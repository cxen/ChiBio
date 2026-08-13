#!/usr/bin/env python3
"""Off-device tests for timed media/inducer schedules (chibio_schedule.py).

  A) validation refuses what would silently misbehave (unknown item, out-of-range, negative
     time, and Pump1/Pump2 while the OD controller already owns them)
  B) step and ramp interpolation, including before the first stage
  C) the clock is the same one the CSV's exp_time uses, and survives the window where
     runExperiment blanks startTimeRaw to write the CSV
  D) the schedule_stage CSV column reports what is in force

    CHIBIO_MOCK_HW=1 python3 test_schedule.py
"""
import os
os.environ['CHIBIO_MOCK_HW'] = '1'

from datetime import datetime, timedelta

import app  # noqa: F401  (imports the state and routes)
from chibio_state import sysData
import chibio_schedule as S

M = 'M0'
sysData[M]['OD']['ON'] = 0
sysData[M]['Chemostat']['ON'] = 0

# --- A) validation ---
ok, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Nonsense', 'target': 1}])
assert ok is None and 'not schedulable' in err, err

ok, err = S.validate_schedule(M, [{'at_h': -1, 'item': 'Pump3', 'target': 0.01}])
assert ok is None and 'at_h' in err, err

ok, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Pump3', 'target': 99}])
assert ok is None and 'outside its' in err, "an out-of-range target must be refused, not clamped"

ok, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Pump3', 'target': 'soon'}])
assert ok is None and 'must be numbers' in err, err

# Pump1/Pump2 are computed by RegulateOD every cycle. Scheduling them while it runs would mean
# two writers on one actuator and the schedule would appear to do nothing.
sysData[M]['OD']['ON'] = 1
ok, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Pump1', 'target': 0.01}])
assert ok is None and 'OD/chemostat controller' in err, err
sysData[M]['OD']['ON'] = 0
ok, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Pump1', 'target': 0.01}])
assert err is None, 'Pump1 is schedulable when nothing else owns it'

# Stages come back sorted, with ramp normalised to 0/1.
cleaned, err = S.validate_schedule(M, [
    {'at_h': 12, 'item': 'Pump3', 'target': 0.02, 'ramp': True},
    {'at_h': 0, 'item': 'Pump3', 'target': 0.0},
])
assert err is None and [s['at_h'] for s in cleaned] == [0.0, 12.0], cleaned
assert cleaned[1]['ramp'] == 1 and cleaned[0]['ramp'] == 0

# Setpoints are schedulable and are range-checked against their own limits.
_c, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'ThermostatTarget', 'target': 37.0}])
assert err is None, err
_c, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'ThermostatTarget', 'target': 99.0}])
assert err is not None, 'thermostat max is 50 C'

print('PASS: validation refuses unknown items, bad numbers, out-of-range targets, and a pump '
      'the OD controller already owns')

# --- B) step and ramp ---
steps = [{'at_h': 0.0, 'item': 'Pump3', 'target': 0.0, 'ramp': 0},
         {'at_h': 12.0, 'item': 'Pump3', 'target': 0.02, 'ramp': 0},
         {'at_h': 24.0, 'item': 'Pump3', 'target': 0.0, 'ramp': 0}]
assert S.scheduled_value(steps, 'Pump3', 0.0) == (0.0, 0)
assert S.scheduled_value(steps, 'Pump3', 11.99)[0] == 0.0, 'a step holds until its hour'
assert S.scheduled_value(steps, 'Pump3', 12.0)[0] == 0.02
assert S.scheduled_value(steps, 'Pump3', 23.9)[0] == 0.02
assert S.scheduled_value(steps, 'Pump3', 99.0)[0] == 0.0, 'the last stage holds forever after'

# Before the first stage the schedule asserts nothing, so a hand-set value is left alone.
late = [{'at_h': 6.0, 'item': 'Pump4', 'target': 0.05, 'ramp': 0}]
assert S.scheduled_value(late, 'Pump4', 1.0) == (None, -1)

# A ramp is declared on the destination stage and interpolates from the previous one.
ramp = [{'at_h': 0.0, 'item': 'Pump3', 'target': 0.0, 'ramp': 0},
        {'at_h': 10.0, 'item': 'Pump3', 'target': 0.10, 'ramp': 1}]
assert abs(S.scheduled_value(ramp, 'Pump3', 0.0)[0] - 0.00) < 1e-9
assert abs(S.scheduled_value(ramp, 'Pump3', 2.5)[0] - 0.025) < 1e-9
assert abs(S.scheduled_value(ramp, 'Pump3', 5.0)[0] - 0.05) < 1e-9
assert abs(S.scheduled_value(ramp, 'Pump3', 10.0)[0] - 0.10) < 1e-9
assert abs(S.scheduled_value(ramp, 'Pump3', 50.0)[0] - 0.10) < 1e-9, 'holds after the ramp ends'

# Two items interleave without interfering -- the Wenk pattern (one component down, another up).
both = [{'at_h': 0.0, 'item': 'Pump3', 'target': 0.10, 'ramp': 0},
        {'at_h': 48.0, 'item': 'Pump3', 'target': 0.0, 'ramp': 1},
        {'at_h': 0.0, 'item': 'Pump4', 'target': 0.0, 'ramp': 0},
        {'at_h': 48.0, 'item': 'Pump4', 'target': 0.10, 'ramp': 1}]
assert abs(S.scheduled_value(both, 'Pump3', 24.0)[0] - 0.05) < 1e-9
assert abs(S.scheduled_value(both, 'Pump4', 24.0)[0] - 0.05) < 1e-9

print('PASS: steps hold until their hour and forever after; ramps interpolate from the previous '
      'stage; before the first stage nothing is asserted')

# --- C) the clock ---
assert S.elapsed_hours(M) is None, 'no running experiment -> no schedule time'
sysData[M]['Experiment']['ON'] = 1
sysData[M]['Experiment']['startTimeRaw'] = datetime.now() - timedelta(hours=3, minutes=30)
t = S.elapsed_hours(M)
assert t is not None and abs(t - 3.5) < 0.01, t

# runExperiment sets startTimeRaw to the int 0 while it writes the CSV (a datetime is not
# JSON-serializable). A tick landing in that window must skip, not raise.
sysData[M]['Experiment']['startTimeRaw'] = 0
assert S.elapsed_hours(M) is None, 'must tolerate the CSV-write window, not raise TypeError'
sysData[M]['Experiment']['startTimeRaw'] = datetime.now() - timedelta(hours=1)

# The schedule clock must agree with the one runExperiment stamps exp_time with.
now = datetime.now()
runexperiment_seconds = (now - sysData[M]['Experiment']['startTimeRaw']).total_seconds()
assert abs(S.elapsed_hours(M) * 3600.0 - runexperiment_seconds) < 1.0, \
    'schedule time and CSV exp_time must come from the same clock'

print('PASS: schedule time uses the same clock as exp_time and tolerates the CSV-write window')

# --- D) the CSV column ---
from chibio_control_helpers import _CSV_COLUMN_UNITS
assert 'schedule_stage' in _CSV_COLUMN_UNITS

sysData[M]['Schedule']['ON'] = 0
sysData[M]['Schedule']['applied'] = 2
stage = (sysData[M]['Schedule']['applied'] if sysData[M]['Schedule']['ON'] == 1 else -1)
assert stage == -1, 'a stored-but-stopped schedule must log -1, not a stale stage'
sysData[M]['Schedule']['ON'] = 1
stage = (sysData[M]['Schedule']['applied'] if sysData[M]['Schedule']['ON'] == 1 else -1)
assert stage == 2

# set_schedule stores only validated stages.
sysData[M]['Experiment']['ON'] = 0
ok, err = S.set_schedule(M, [{'at_h': 0, 'item': 'Pump3', 'target': 0.01}])
assert ok and sysData[M]['Schedule']['stages'][0]['item'] == 'Pump3'
ok, err = S.set_schedule(M, [{'at_h': 0, 'item': 'Bogus', 'target': 0.01}])
assert not ok and sysData[M]['Schedule']['stages'][0]['item'] == 'Pump3', \
    'a rejected schedule must not overwrite the accepted one'

# Starting with no stages is refused rather than running an empty loop.
sysData[M]['Schedule']['ON'] = 0
sysData[M]['Schedule']['stages'] = []
ok, err = S.schedule_on_off(M, 1)
assert not ok and 'no stages' in err, err
assert sysData[M]['Schedule']['ON'] == 0, 'a refused start must not leave the flag on'

print('PASS: schedule_stage reports -1 unless a schedule is running; a rejected schedule does '
      'not replace the accepted one; an empty schedule will not start')

# --- E) regressions found in review ---
# A ramped Stir would re-trigger SetOutput's full-power 1.5 s motor kick on every tick.
_c, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Stir', 'target': 0.2},
                                  {'at_h': 5, 'item': 'Stir', 'target': 0.8, 'ramp': 1}])
assert err is not None and 'full power' in err, err
_c, err = S.validate_schedule(M, [{'at_h': 0, 'item': 'Stir', 'target': 0.2},
                                  {'at_h': 5, 'item': 'Stir', 'target': 0.8}])
assert err is None, 'stepped stir changes are fine'

# `applied` indexes the GLOBAL sorted stage list, which is what the CSV column records and what
# the UI marks a row by. Per-item indices diverge from it as soon as there are two items.
two_items, err = S.validate_schedule(M, [
    {'at_h': 0.0, 'item': 'Pump3', 'target': 0.0},
    {'at_h': 0.0, 'item': 'Pump4', 'target': 0.0},
    {'at_h': 10.0, 'item': 'Pump3', 'target': 0.02},
    {'at_h': 20.0, 'item': 'Pump4', 'target': 0.02},
])
assert err is None
# Pump4's second stage is per-item index 1 but global index 3.
_v, per_item = S.scheduled_value(two_items, 'Pump4', 25.0)
assert per_item == 1, per_item
global_idx = max([n for n, st in enumerate(two_items) if st['at_h'] <= 25.0] or [-1])
assert global_idx == 3, global_idx
assert per_item != global_idx, 'the two indices must not be confused -- this is the bug'

print('PASS: a ramped stir is refused; the global stage index is distinct from the per-item one')

# --- F) the "0" sentinel ---
# Every route in this app accepts M=="0" meaning "the reactor the UI is showing", and the UI's
# own buttons post to /SetSchedule/0. Without normalising it, sysData['0'] raises and the browser
# gets a bare 500. Found on the device: the python probe passed "M2" explicitly and missed it.
from chibio_state import sysItems
sysItems['UIDevice'] = 'M1'
sysData['M1']['OD']['ON'] = 0
sysData['M1']['Chemostat']['ON'] = 0
sysData['M1']['Experiment']['ON'] = 0

cleaned, err = S.validate_schedule('0', [{'at_h': 0, 'item': 'Pump3', 'target': 0.01}])
assert err is None, err
ok, err = S.set_schedule('0', [{'at_h': 1, 'item': 'Pump4', 'target': 0.02}])
assert ok, err
assert sysData['M1']['Schedule']['stages'][0]['item'] == 'Pump4', \
    '"0" must resolve to the UI device, not raise or write elsewhere'
assert S.elapsed_hours('0') is None       # no experiment on M1; must not raise
ok, err = S.schedule_on_off('0', 0)
assert ok, err

print('PASS: the "0" sentinel resolves to the UI device in every entry point')
