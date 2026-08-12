"""Off-device tests for the per-reactor measurement mutex and the experiment watchdog.

Run: CHIBIO_MOCK_HW=1 python3 test_concurrency.py

Covers the two live-run defects of 2026-08-11: a FluorescenceScan corrupting a concurrent
OD row (unflagged raw=0), and the same collision killing an experiment thread outright.
"""
import os
import threading
import time

os.environ.setdefault('CHIBIO_MOCK_HW', '1')

from chibio_hardware import measurement_sequence
from chibio_state import sysData, sysDevices
import app


def test_mutex_serializes_sequences():
    # Two threads each run an on -> read -> off sequence on the SAME reactor. Without the
    # mutex these interleave and one thread's "off" lands inside the other's read -- the
    # mechanism that produced raw=0 with valid=1.
    events = []
    barrier = threading.Barrier(2)

    def sequence(tag):
        barrier.wait()
        with measurement_sequence('M0'):
            events.append((tag, 'on'))
            time.sleep(0.02)          # the window a racing thread would slip into
            events.append((tag, 'read'))
            time.sleep(0.02)
            events.append((tag, 'off'))

    threads = [threading.Thread(target=sequence, args=(t,)) for t in ('scan', 'cycle')]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(events) == 6, events
    first = events[0][0]
    assert [e[0] for e in events[:3]] == [first] * 3, 'sequences interleaved: %r' % (events,)
    assert [e[1] for e in events[:3]] == ['on', 'read', 'off'], events
    assert [e[1] for e in events[3:]] == ['on', 'read', 'off'], events
    print('PASS mutex serializes whole on->read->off sequences')


def test_mutex_is_reentrant():
    # runExperiment holds the guard across its replicate series while each measure_od inside
    # takes it again via get_transmission. A non-reentrant lock would deadlock the cycle.
    done = []

    def nested():
        with measurement_sequence('M1'):
            with measurement_sequence('M1'):
                done.append(True)

    t = threading.Thread(target=nested)
    t.start()
    t.join(timeout=5.0)
    assert not t.is_alive(), 'nested acquisition deadlocked'
    assert done == [True]
    print('PASS mutex is re-entrant for the holding thread')


def test_mutex_is_per_reactor():
    # Different reactors must still measure concurrently -- serializing them would make the
    # per-cycle bus work scale with reactor count.
    started = threading.Event()
    overlapped = []

    def hold():
        with measurement_sequence('M2'):
            started.set()
            time.sleep(0.15)

    t = threading.Thread(target=hold)
    t.start()
    started.wait(timeout=2.0)
    t0 = time.time()
    with measurement_sequence('M3'):
        overlapped.append(time.time() - t0)
    t.join()
    assert overlapped[0] < 0.1, 'M3 blocked on M2: %.3fs' % overlapped[0]
    print('PASS mutex is per-reactor (M3 did not block on M2)')


def _set_experiment(M, present, on, cycles, last, cycleTime=60.0):
    sysData[M]['present'] = present
    sysData[M]['Experiment']['ON'] = on
    sysData[M]['Experiment']['cycles'] = cycles
    sysData[M]['Experiment']['lastCycleMonotonic'] = last
    sysData[M]['Experiment']['cycleTime'] = cycleTime


def test_watchdog_flags_only_the_dead_reactor():
    now = 10000.0
    for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        _set_experiment(M, 0, 0, 0, 0.0)
    _set_experiment('M0', 1, 1, 50, now - 30)     # healthy
    _set_experiment('M1', 1, 1, 50, now - 400)    # silent > 3 x 60 s
    _set_experiment('M2', 1, 1, 50, now - 61)     # late but within tolerance
    running, stalled = app.classify_experiment_liveness(now)
    assert running == ['M0', 'M1', 'M2'], running
    assert stalled == ['M1'], stalled
    print('PASS watchdog flags only the stalled reactor')


def test_watchdog_ignores_idle_and_never_started():
    now = 10000.0
    for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        _set_experiment(M, 0, 0, 0, 0.0)
    _set_experiment('M0', 1, 0, 50, now - 9999)   # experiment off
    _set_experiment('M1', 0, 1, 50, now - 9999)   # reactor absent
    _set_experiment('M2', 1, 1, 0, 0.0)           # started, no cycle completed yet
    running, stalled = app.classify_experiment_liveness(now)
    assert running == [], running
    assert stalled == [], stalled
    print('PASS watchdog ignores idle, absent and not-yet-cycled reactors')


def test_liveness_stamp_and_comparison_use_one_clock():
    # Regression, found on hardware: the cycle stamped time.monotonic() while the watchdog
    # compared against time.time(). Their offset (1,786,529,500 s) made every reactor read as
    # permanently stalled. The other watchdog tests cannot catch this -- they pass a synthetic
    # `now` alongside a synthetic stamp, so the two agree by construction. This one exercises
    # the REAL clock on both sides.
    import chibio_experiment  # noqa: F401  (same import path runExperiment uses)
    for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        _set_experiment(M, 0, 0, 0, 0.0)
    M = 'M0'
    _set_experiment(M, 1, 1, 5, 0.0)
    app.stamp_cycle_complete(M)                        # the exact call a finished cycle makes
    # Pin the clock explicitly, so swapping it for time.time() fails here rather than on the rig.
    assert abs(sysData[M]['Experiment']['lastCycleMonotonic'] - time.monotonic()) < 1.0, \
        'the cycle stamp is not on time.monotonic()'
    running, stalled = app.classify_experiment_liveness(app.liveness_now())
    assert running == [M], running
    assert stalled == [], (
        'a reactor that just completed a cycle reads as stalled -- the stamp and the '
        'comparison are on different clocks')

    # And a genuinely old stamp must still be caught.
    _set_experiment(M, 1, 1, 5, app.liveness_now() - 400)
    _, stalled = app.classify_experiment_liveness(app.liveness_now())
    assert stalled == [M], 'a genuinely stale reactor was not flagged'
    print('PASS liveness stamp and comparison share one clock')


def test_watchdog_distinguishes_all_stalled_from_one_dead():
    # INVARIANTS 5: every reactor stalling at once is a bus/worker fault, not a dead thread.
    # Auto-recovery once restarted all five into fresh unblanked CSVs by missing this.
    now = 10000.0
    for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
        _set_experiment(M, 0, 0, 0, 0.0)
    for M in ['M0', 'M1', 'M2', 'M3']:
        _set_experiment(M, 1, 1, 50, now - 400)
    running, stalled = app.classify_experiment_liveness(now)
    assert running == stalled == ['M0', 'M1', 'M2', 'M3'], (running, stalled)
    assert len(stalled) == len(running), 'caller must refuse to auto-restart this case'
    print('PASS watchdog can tell "all stalled" from "one dead thread"')


def test_restart_rearms_running_and_restores_stir():
    # The recovery the operator had to perform by hand. Two things must happen that
    # ExperimentStartStop alone does not do: clear `running` (left at 1 by a thread that died
    # before its finally, which would make every future start silently refuse), and re-assert
    # stir (the cycle turns it off to measure, so a dead thread strands the culture unstirred).
    M = 'M5'
    outputs = []
    started = []
    orig_run = app.runExperiment
    orig_set = app.set_output_on_sync
    try:
        app.runExperiment = lambda m, p: started.append(m)
        app.set_output_on_sync = lambda m, item, force: outputs.append((m, item, force))
        sysDevices[M]['Experiment']['running'] = 1      # as a thread that died mid-cycle leaves it
        sysData[M]['Experiment']['ON'] = 1
        sysData[M]['Experiment']['cycles'] = 42
        sysData[M]['Experiment']['lastCycleMonotonic'] = 1.0

        app._restart_stalled_experiment(M, 400.0)
        time.sleep(0.3)
    finally:
        app.runExperiment = orig_run
        app.set_output_on_sync = orig_set
        sysData[M]['Experiment']['ON'] = 0

    assert (M, 'Stir', 1) in outputs, 'stir was not re-asserted: %r' % (outputs,)
    assert started == [M], 'the experiment loop was not restarted: %r' % (started,)
    assert sysDevices[M]['Experiment']['running'] == 1, 'running flag not re-armed'
    assert sysData[M]['Experiment']['lastCycleMonotonic'] > 1.0, \
        'lastCycleMonotonic not refreshed -- the watchdog would immediately restart it again'
    assert sysData[M]['Experiment']['cycles'] == 42, \
        'cycles must be preserved so the run resumes into the same CSV'
    print('PASS restart re-arms running, restores stir and preserves the run')


def test_never_starts_a_second_loop_over_a_live_thread():
    # The dangerous case: a thread that is STALLED but ALIVE (blocked on the bus lock, the
    # leading suspect for these stalls). threadCount supersession only bites when the old loop
    # re-checks its while condition, so a blocked thread wakes and finishes its cycle anyway --
    # driving RegulateOD and appending a CSV row alongside the replacement. Two dilution
    # decisions per cycle on a live culture is worse than the stall.
    M = 'M6'
    started = []
    release = threading.Event()
    orig_run = app.runExperiment
    orig_set = app.set_output_on_sync
    alive = threading.Thread(target=lambda: release.wait(timeout=5.0))
    alive.daemon = True
    alive.start()
    try:
        app.runExperiment = lambda m, p: started.append(m)
        app.set_output_on_sync = lambda m, item, force: None
        sysDevices[M]['Experiment']['thread'] = alive
        sysDevices[M]['Experiment']['running'] = 1
        sysData[M]['Experiment']['ON'] = 1
        sysData[M]['Experiment']['cycles'] = 10

        app._restart_stalled_experiment(M, 400.0)
        assert started == [], 'started a second loop while the old thread was still alive'
        assert sysDevices[M]['Experiment']['running'] == 1, 'running flag cleared under a live thread'

        release.set()
        alive.join(timeout=5.0)
        app._restart_stalled_experiment(M, 400.0)   # now genuinely dead
        time.sleep(0.2)
        assert started == [M], 'a genuinely dead thread was not replaced: %r' % (started,)
    finally:
        release.set()
        app.runExperiment = orig_run
        app.set_output_on_sync = orig_set
        sysData[M]['Experiment']['ON'] = 0
    print('PASS a stalled-but-alive thread is never duplicated; a dead one is replaced')


def _run_experiment_until_exit(M, supersede):
    """Drive one runExperiment call to its `finally`, optionally superseded on the way out."""
    import app as _app
    import chibio_experiment
    orig = (_app.set_output_on_sync, _app.turnEverythingOff, _app.addTerminal)

    def fake_output(m, item, force):
        # Fires as the cycle turns stirring off, i.e. inside the loop body. Stop the
        # experiment so the cycle takes its early exit, and optionally hand the reactor to a
        # newer thread first.
        if supersede:
            sysData[M]['Experiment']['threadCount'] = 77
        sysData[M]['Experiment']['ON'] = 0

    _app.set_output_on_sync = fake_output
    _app.turnEverythingOff = lambda m: None
    _app.addTerminal = lambda m, t: None
    try:
        sysData[M]['Experiment']['ON'] = 1
        sysDevices[M]['Experiment']['running'] = 1
        chibio_experiment.runExperiment(M, 'placeholder')
    finally:
        _app.set_output_on_sync, _app.turnEverythingOff, _app.addTerminal = orig
        sysData[M]['Experiment']['ON'] = 0


def test_superseded_thread_does_not_clear_running():
    # A replaced thread reaching its `finally` must not clear `running` out from under its
    # replacement -- that defeats the duplicate-launch guard in ExperimentStartStop and would
    # let a third loop start on the same reactor.
    M = 'M7'
    _run_experiment_until_exit(M, supersede=False)
    assert sysDevices[M]['Experiment']['running'] == 0, \
        'an un-superseded thread must clear `running` on the way out'

    _run_experiment_until_exit(M, supersede=True)
    assert sysDevices[M]['Experiment']['running'] == 1, \
        'a superseded thread cleared `running`, so a duplicate loop could start'
    sysDevices[M]['Experiment']['running'] = 0
    print('PASS `running` is cleared by the owning thread only, never by a superseded one')


def test_rapid_measurements_are_coalesced_not_queued():
    # The soft-lock: measurement routes are fire-and-forget and settle in ~1.6 s, so a burst
    # of clicks used to spawn a thread each. With the per-reactor mutex they would all queue
    # instead of racing -- still a pile of blocked threads. A second "measure now" tells us
    # nothing the first will not, so it must be dropped.
    running = []
    peak = [0]
    guard = threading.Lock()

    def slow_measure(M):
        with guard:
            running.append(M)
            peak[0] = max(peak[0], len(running))
        time.sleep(0.15)
        with guard:
            running.remove(M)

    accepted = [app.run_measurement(slow_measure, 'M0') for _ in range(10)]
    time.sleep(0.6)
    assert peak[0] == 1, 'measurements ran concurrently on one reactor: peak %d' % peak[0]
    assert accepted[0] is True, 'the first request must run'
    assert sum(1 for a in accepted if a) == 1, 'expected 1 accepted, got %d' % sum(1 for a in accepted if a)
    # And the reactor must be usable again afterwards.
    assert app.run_measurement(slow_measure, 'M0') is True
    time.sleep(0.3)
    print('PASS rapid measurement requests coalesce to one in flight per reactor')


def test_measurement_coalescing_is_per_reactor():
    def quick(M):
        time.sleep(0.1)

    assert app.run_measurement(quick, 'M1') is True
    assert app.run_measurement(quick, 'M2') is True, 'M2 must not be blocked by M1'
    time.sleep(0.3)
    print('PASS measurement coalescing is per-reactor')


def test_distinct_measurements_are_not_dropped():
    # Regression: coalescing keyed on the reactor alone silently dropped every measurement
    # after the first in a back-to-back burst. The device self-test posts Internal, External,
    # OD and FP with no delay between them -- ThermometerExternal then read 0.00 C on all four
    # reactors, because the request never ran and the stale value stayed in place.
    ran = []
    guard = threading.Lock()

    def measure_temp(M, which):
        time.sleep(0.1)
        with guard:
            ran.append(('temp', which))

    def measure_od(M):
        time.sleep(0.1)
        with guard:
            ran.append(('od',))

    def measure_fp(M):
        time.sleep(0.1)
        with guard:
            ran.append(('fp',))

    accepted = [
        app.run_measurement(measure_temp, 'M4', 'Internal'),
        app.run_measurement(measure_temp, 'M4', 'External'),
        app.run_measurement(measure_od, 'M4'),
        app.run_measurement(measure_fp, 'M4'),
    ]
    assert all(accepted), 'distinct measurements were dropped: %r' % (accepted,)
    time.sleep(0.8)
    assert ('temp', 'External') in ran, 'ThermometerExternal was dropped: %r' % (ran,)
    assert ('temp', 'Internal') in ran and ('od',) in ran and ('fp',) in ran, ran
    assert len(ran) == 4, ran
    # ...while a repeat of the SAME measurement is still coalesced.
    again = [app.run_measurement(measure_temp, 'M4', 'External') for _ in range(5)]
    assert sum(1 for a in again if a) == 1, again
    time.sleep(0.3)
    print('PASS distinct measurements all run; only exact repeats are coalesced')


def test_background_threads_are_capped():
    # Backstop: a command burst must not be able to spawn threads without limit.
    release = threading.Event()

    def blocker():
        release.wait(timeout=5.0)

    started = [app.run_background(blocker) for _ in range(app._MAX_BACKGROUND_THREADS + 8)]
    accepted = [t for t in started if t is not None]
    refused = [t for t in started if t is None]
    assert len(accepted) <= app._MAX_BACKGROUND_THREADS, len(accepted)
    assert refused, 'the cap never engaged'
    release.set()
    for t in accepted:
        t.join(timeout=5.0)
    # Count must return to zero so the cap is not a one-way ratchet.
    deadline = time.time() + 5.0
    while app._background_count[0] > 0 and time.time() < deadline:
        time.sleep(0.05)
    assert app._background_count[0] == 0, app._background_count[0]
    assert app.run_background(lambda: None) is not None, 'cap did not release'
    print('PASS background threads are capped and the cap releases')


def test_negative_corrected_transmission_cannot_raise():
    # Dark subtraction can push corrected transmission below zero; log10 of a negative would
    # propagate out of measure_od and kill the calling experiment thread.
    from chibio_measurements import _od_from_transmission
    sysData['M0']['OD0']['target'] = 10000.0
    for trans in (-5.0, -1.0, 0.0, 0.0005):
        assert _od_from_transmission('M0', 'LASER650', trans) == 0, trans
    assert _od_from_transmission('M0', 'LASER650', 5000.0) > 0
    print('PASS negative dark-corrected transmission returns 0 instead of raising')


def test_characterise_refuses_during_an_experiment():
    # The sweep drives LASER650 from 0 to full, so no OD reading taken during it is
    # meaningful -- a concurrent cycle logged OD 9.99 while the sweep sat near zero power.
    # The mutex makes each read atomic but cannot hold a shared power target still between
    # them, so the routine has to decline rather than corrupt the run.
    M = 'M0'
    sysData[M]['present'] = 1
    sysData[M]['Experiment']['ON'] = 1
    try:
        client = app.application.test_client()
        r = client.post('/CharacteriseDevice/%s/C1' % M)
        assert r.status_code == 409, 'expected refusal, got %s' % r.status_code
    finally:
        sysData[M]['Experiment']['ON'] = 0
    print('PASS characterisation refuses to run during an experiment')


def test_characterise_restores_power_targets():
    # Left unrestored, every LED and the laser sit at 1.0 (the last level swept). The blank
    # was taken at LASER650=0.5, so OD silently rescales -- measured 3.17 -> 2.60 on M0.
    import app as _app
    M = 'M1'
    sysData[M]['present'] = 1
    sysData[M]['Experiment']['ON'] = 0
    swept = ['LEDA', 'LEDB', 'LEDC', 'LEDD', 'LEDE', 'LEDF', 'LEDG', 'LASER650']
    before = {}
    for i, item in enumerate(swept):
        sysData[M][item]['target'] = 0.5 if item == 'LASER650' else 0.1 + i * 0.01
        before[item] = sysData[M][item]['target']

    orig = (_app.set_output_on_sync, _app.set_output_target_sync, _app.get_spectrum,
            _app.addTerminal)
    calls = []

    def fake_target(m, item, value):
        sysData[m][item]['target'] = float(value)
        calls.append((item, float(value)))

    _app.set_output_on_sync = lambda m, item, force: None
    _app.set_output_target_sync = fake_target
    _app.get_spectrum = lambda m, gain: None
    _app.addTerminal = lambda m, t: None
    try:
        _app.CharacteriseDevice2(M)
    finally:
        (_app.set_output_on_sync, _app.set_output_target_sync, _app.get_spectrum,
         _app.addTerminal) = orig

    assert any(v == 1.0 for _, v in calls), 'the sweep did not actually run'
    for item in swept:
        assert sysData[M][item]['target'] == before[item], \
            '%s left at %s, expected %s' % (item, sysData[M][item]['target'], before[item])
    print('PASS characterisation restores every power target it swept')


if __name__ == '__main__':
    test_mutex_serializes_sequences()
    test_mutex_is_reentrant()
    test_mutex_is_per_reactor()
    test_watchdog_flags_only_the_dead_reactor()
    test_watchdog_ignores_idle_and_never_started()
    test_liveness_stamp_and_comparison_use_one_clock()
    test_watchdog_distinguishes_all_stalled_from_one_dead()
    test_restart_rearms_running_and_restores_stir()
    test_never_starts_a_second_loop_over_a_live_thread()
    test_superseded_thread_does_not_clear_running()
    test_rapid_measurements_are_coalesced_not_queued()
    test_measurement_coalescing_is_per_reactor()
    test_distinct_measurements_are_not_dropped()
    test_background_threads_are_capped()
    test_negative_corrected_transmission_cannot_raise()
    test_characterise_refuses_during_an_experiment()
    test_characterise_restores_power_targets()
    print('\nAll concurrency tests passed.')
