"""Timed media / inducer schedules: a first-class notion of "at hour X, set Y to Z".

Why this exists. Until now the rig offered a *fixed* OD or chemostat setpoint plus free-form
`CustomProgram`s, and nothing in between -- so every published run that needed a changing
condition did it by hand. Joshi et al. changed inducer levels by physically swapping the media
reservoir every 12 h; Wenk et al. drove a 150-day adaptive-evolution experiment with a manually
scheduled medium-composition ramp (glycine down, formate up) where the turbidostat only held OD
constant and the entire selection pressure came from the schedule. Both are a list of
(time -> target) pairs that a machine should be following, not a person.
See docs/chibio-usage-literature-review.md and TODO P8.

What it drives. Pump1/Pump2 belong to RegulateOD (Pump2's rate is computed from Pump1's), so
scheduling them while OD control is on would mean two writers on one actuator; that combination
is refused. **Pump3 and Pump4 are free** -- nothing in the codebase drives them -- which is
exactly the inducer / second-reservoir channel the two studies above lacked. Setpoints
(`ODTarget`, `ThermostatTarget`) are also schedulable, which covers a dilution-rate or
temperature ramp.

Clock. Elapsed time comes from `datetime.now() - Experiment['startTimeRaw']`, the SAME
expression `runExperiment` uses to stamp `exp_time`, via one shared helper. A schedule that
measured time differently from the CSV it is recorded in would put a stage boundary at a
different place in the data than in reality -- the same class of bug as the monotonic-vs-walltime
liveness mismatch found on 2026-08-12, which unit tests could not catch because they passed a
synthetic clock to both sides.
"""
import logging
import time
from datetime import datetime

from chibio_state import sysData, sysDevices, sysItems

logger = logging.getLogger('chibio')

_TICK_SECONDS = 10.0
# Only write an output when the scheduled value actually moves. Pump targets live in the 0-0.25
# range, so this is well below anything meaningful while still stopping a ramp from issuing an
# I2C write every tick for a change in the 6th decimal.
_MIN_CHANGE = 1e-4

# Outputs the schedule may drive, and the two setpoints it may move. Anything else is refused --
# a typo must not silently do nothing, and the schedule must never reach the watchdog or the
# multiplexer.
SCHEDULABLE_OUTPUTS = ('Pump1', 'Pump2', 'Pump3', 'Pump4', 'Stir', 'Heat', 'UV', 'LASER650',
                       'LEDA', 'LEDB', 'LEDC', 'LEDD', 'LEDE', 'LEDF', 'LEDG', 'LEDH', 'LEDI')
SCHEDULABLE_SETPOINTS = ('ODTarget', 'ThermostatTarget')
SCHEDULABLE = SCHEDULABLE_OUTPUTS + SCHEDULABLE_SETPOINTS


def _device(M):
    # "0" is the sentinel for the reactor the UI currently has selected. Every route in this
    # app accepts it, so every entry point here must resolve it before touching sysData --
    # sysData has no '0' key and would raise, which the UI sees as a 500 with no explanation.
    M = str(M)
    return sysItems['UIDevice'] if M == "0" else M


def elapsed_hours(M):
    """Hours since the experiment started, on the clock the CSV's exp_time uses.

    Returns None when there is no running experiment to measure against.

    `startTimeRaw` is a datetime, and `runExperiment` sets it to the int 0 for the duration of
    each CSV write (simplejson cannot serialize a datetime). A tick landing in that window would
    raise TypeError on the subtraction, so treat a non-datetime as "not available right now" and
    skip -- at a 10 s tick, missing one is invisible against schedule stages measured in hours.
    """
    M = _device(M)
    if sysData[M]['Experiment']['ON'] != 1:
        return None
    start = sysData[M]['Experiment']['startTimeRaw']
    if not isinstance(start, datetime):
        return None
    return (datetime.now() - start).total_seconds() / 3600.0


def validate_schedule(M, stages):
    """Check a schedule before accepting it. Returns (cleaned_stages, error_or_None).

    Pure -- no state is touched -- so the route can refuse a bad schedule outright rather than
    discovering the problem in a control thread an hour later.
    """
    M = _device(M)
    if not isinstance(stages, list):
        return None, 'schedule must be a list of stages'
    cleaned = []
    for n, st in enumerate(stages):
        if not isinstance(st, dict):
            return None, 'stage %d is not an object' % n
        item = str(st.get('item', ''))
        if item not in SCHEDULABLE:
            return None, ('stage %d: %r is not schedulable (allowed: %s)'
                          % (n, item, ', '.join(SCHEDULABLE)))
        try:
            at_h = float(st.get('at_h'))
            target = float(st.get('target'))
        except (TypeError, ValueError):
            return None, 'stage %d: at_h and target must be numbers' % n
        if at_h < 0:
            return None, 'stage %d: at_h must be >= 0 (hours after the experiment starts)' % n
        # Clamp to the item's own declared range rather than trusting the caller. Out-of-range is
        # an error, not something to silently saturate: a mistyped pump rate should be rejected
        # while the operator is looking at it.
        if item in SCHEDULABLE_OUTPUTS:
            lo, hi = sysData[M][item]['min'], sysData[M][item]['max']
        elif item == 'ODTarget':
            lo, hi = sysData[M]['OD']['min'], sysData[M]['OD']['max']
        else:
            lo, hi = sysData[M]['Thermostat']['min'], sysData[M]['Thermostat']['max']
        if not (lo <= target <= hi):
            return None, ('stage %d: %s target %g is outside its %g..%g range'
                          % (n, item, target, lo, hi))
        ramp = 1 if st.get('ramp') else 0
        if ramp and item == 'Stir':
            # SetOutput's Stir branch hard-starts the motor at FULL power for 1.5 s on any target
            # change (app.py, INVARIANTS 6). A ramp re-issues a value every tick, so this would
            # kick the stirrer to full every 10 s for as long as the ramp lasts. Steps are fine.
            return None, ('stage %d: Stir cannot be ramped -- every stir change restarts the '
                          'motor at full power for 1.5 s, so a ramp would kick it every tick. '
                          'Use separate step stages instead.' % n)
        cleaned.append({'at_h': at_h, 'item': item, 'target': target, 'ramp': ramp})
    cleaned.sort(key=lambda s: (s['at_h'], s['item']))

    # Two writers on one actuator. RegulateOD computes Pump2 from Pump1 every cycle, so a
    # scheduled value would be overwritten within a cycle and the operator would see the
    # schedule "not working" with nothing logged. Refuse the combination up front.
    if sysData[M]['OD']['ON'] == 1 or sysData[M]['Chemostat']['ON'] == 1:
        for st in cleaned:
            if st['item'] in ('Pump1', 'Pump2'):
                return None, ('%s is driven by the OD/chemostat controller while that is on -- '
                              'schedule Pump3/Pump4 for inducer or second-reservoir feeds instead'
                              % st['item'])
    return cleaned, None


def scheduled_value(stages, item, t_h):
    """The value `item` should hold at elapsed time `t_h`, and the stage index that set it.

    Returns (None, -1) before the item's first stage -- the schedule then leaves whatever the
    operator set by hand alone, rather than asserting a value nobody asked for.

    `ramp` is declared on the DESTINATION stage: a ramped stage interpolates linearly from the
    previous stage for the same item up to its own target. That is what a medium-composition
    ramp looks like when it is written down ("reach 20 mM by hour 48"), and it means a plain
    step schedule needs no extra keys at all.
    """
    own = [s for s in stages if s['item'] == item]
    own.sort(key=lambda s: s['at_h'])
    if not own or t_h < own[0]['at_h']:
        return None, -1
    i = 0
    for n, s in enumerate(own):
        if s['at_h'] <= t_h:
            i = n
        else:
            break
    current = own[i]
    nxt = own[i + 1] if i + 1 < len(own) else None
    if nxt is not None and nxt['ramp']:
        span = nxt['at_h'] - current['at_h']
        if span > 0:
            frac = max(0.0, min(1.0, (t_h - current['at_h']) / span))
            return current['target'] + frac * (nxt['target'] - current['target']), i
    return current['target'], i


def _apply(M, item, value):
    # Function-local imports: app imports this module at top level (circular by design).
    from app import set_output_on_sync, set_output_target_sync
    if item == 'ODTarget':
        sysData[M]['OD']['target'] = value
        return
    if item == 'ThermostatTarget':
        sysData[M]['Thermostat']['target'] = value
        return
    set_output_target_sync(M, item, value)
    # A target with nothing switched on does nothing, which would look like the schedule being
    # ignored. Drive the ON flag from the value: a scheduled 0 means "off", not "on at zero".
    # Only write it when it actually flips -- every one of these is an I2C transaction under the
    # global bus lock, and for Stir it also restarts the motor at full power.
    want_on = 1 if abs(value) > _MIN_CHANGE else 0
    if sysData[M][item]['ON'] != want_on:
        set_output_on_sync(M, item, want_on)


def RunSchedule(M):
    """Follow this reactor's schedule for as long as it and the experiment are both running."""
    from app import addTerminal
    from chibio_control_helpers import logEvent
    M = _device(M)
    sysData[M]['Schedule']['threadCount'] = (sysData[M]['Schedule']['threadCount'] + 1) % 100
    currentThread = sysData[M]['Schedule']['threadCount']
    sysDevices[M]['scheduleRunning'] = 1
    addTerminal(M, 'Schedule started (' + str(len(sysData[M]['Schedule']['stages'])) + ' stages)')
    last_written = {}
    last_stage = {}
    try:
        while (sysData[M]['Schedule']['ON'] == 1
               and sysData[M]['Schedule']['threadCount'] == currentThread):
            try:
                t_h = elapsed_hours(M)
                if t_h is None:
                    # Either no experiment is running, or one is and runExperiment has blanked
                    # startTimeRaw for the moment it takes to write the CSV. Only the first is
                    # worth reporting -- saying "waiting to start" mid-run would be false, and at
                    # a 10 s tick it would flicker there once a cycle.
                    if sysData[M]['Experiment']['ON'] != 1:
                        sysData[M]['Schedule']['status'] = 'waiting for the experiment to start'
                    time.sleep(_TICK_SECONDS)
                    continue
                stages = sysData[M]['Schedule']['stages']
                items = []
                for s in stages:
                    if s['item'] not in items:
                        items.append(s['item'])
                # How far down the schedule we are, as an index into the GLOBAL sorted stage list.
                # Per-item indices are not interchangeable with this: with two items in the
                # schedule they diverge immediately, and both the CSV column and the UI's
                # in-force row marker are expressed against the global list.
                active = -1
                for n, s in enumerate(stages):
                    if s['at_h'] <= t_h:
                        active = n
                for item in items:
                    value, idx = scheduled_value(stages, item, t_h)
                    if value is None:
                        continue
                    if item in last_stage and last_stage[item] != idx:
                        # Stage boundaries are the discontinuities an analyst has to know about,
                        # so they go in the events sidecar next to FP-config and blank changes.
                        # logEvent stamps its `exp_time` from the last COMPLETED cycle, so with a
                        # 60 s cycle and a 10 s tick that field can sit up to a cycle behind the
                        # transition. `at_h` in the detail is the real time it happened -- use it,
                        # not exp_time, when lining a stage change up against the data.
                        logEvent(M, 'schedule_stage', {'item': item, 'stage': idx,
                                                       'target': round(value, 6), 'at_h': round(t_h, 4)})
                        addTerminal(M, 'Schedule: %s -> %g (stage %d)' % (item, value, idx))
                    last_stage[item] = idx
                    if abs(last_written.get(item, value + 1) - value) >= _MIN_CHANGE:
                        _apply(M, item, value)
                        last_written[item] = value
                sysData[M]['Schedule']['applied'] = active
                sysData[M]['Schedule']['status'] = ('stage %d, t=%.2f h' % (active, t_h)
                                                    if active >= 0 else
                                                    'before the first stage (t=%.2f h)' % t_h)
            except Exception:
                # A schedule must not take the experiment down with it -- same discipline as the
                # cycle body in runExperiment.
                logger.exception('Schedule tick failed on %s', M)
            time.sleep(_TICK_SECONDS)
    finally:
        # Only if we are still the current thread. A superseded thread clearing this would let a
        # third start spawn a duplicate alongside the live one.
        if sysData[M]['Schedule']['threadCount'] == currentThread:
            sysDevices[M]['scheduleRunning'] = 0
            sysData[M]['Schedule']['status'] = 'stopped'
            addTerminal(M, 'Schedule stopped')


def set_schedule(M, stages):
    """Validate and store a schedule. Returns (ok, error)."""
    from app import addTerminal
    from chibio_control_helpers import logEvent
    M = _device(M)
    cleaned, err = validate_schedule(M, stages)
    if err:
        addTerminal(M, 'Schedule rejected: ' + err)
        return False, err
    sysData[M]['Schedule']['stages'] = cleaned
    sysData[M]['Schedule']['applied'] = -1
    addTerminal(M, 'Schedule set: ' + str(len(cleaned)) + ' stages')
    logEvent(M, 'schedule_set', {'stages': cleaned})
    return True, None


def schedule_on_off(M, value):
    """Start or stop following the schedule. Returns (ok, error)."""
    from app import addTerminal, run_background
    M = _device(M)
    value = int(value)
    if value == 1:
        if not sysData[M]['Schedule']['stages']:
            return False, 'no stages set'
        # Re-validate at start: OD control may have been switched on since the schedule was
        # accepted, which would put two writers on Pump1/Pump2.
        _cleaned, err = validate_schedule(M, sysData[M]['Schedule']['stages'])
        if err:
            addTerminal(M, 'Schedule refused: ' + err)
            return False, err
        sysData[M]['Schedule']['ON'] = 1
        if sysDevices[M].get('scheduleRunning', 0) == 0:
            run_background(RunSchedule, M)
    else:
        sysData[M]['Schedule']['ON'] = 0
    return True, None
