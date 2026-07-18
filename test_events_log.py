#!/usr/bin/env python3
"""Off-device test for the mid-run events log (logEvent):
  - no-op unless an experiment is running (nothing to describe otherwise)
  - appends timestamped records to <startTime>_<M>_events.json as a JSON array
  - accumulates across calls (append, not overwrite); records type/detail/exp_time
  - atomic write leaves no temp file behind

    CHIBIO_MOCK_HW=1 python3 test_events_log.py
"""
import json
import os
import tempfile

os.environ['CHIBIO_MOCK_HW'] = '1'

import chibio_state
from chibio_control_helpers import logEvent

M = 'M0'
sd = chibio_state.sysData[M]
sd['time'] = {'record': [0.0, 123.0]}
sd['Experiment'] = {'ON': 0, 'startTime': '2026-07-16 12_00_00'}

fname = '2026-07-16 12_00_00_%s_events.json' % M

with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)

    # (a) no-op when no experiment is running
    logEvent(M, 'fp_config', {'slot': 'FP3', 'on': 1})
    assert not os.path.isfile(fname), 'must not write an events file when the experiment is off'

    # (b) logs while running -- a JSON array with the expected fields
    sd['Experiment']['ON'] = 1
    logEvent(M, 'fp_config', {'slot': 'FP3', 'on': 1, 'led': 'LEDB', 'gain': 'x10'})
    with open(fname) as f:
        events = json.load(f)
    assert isinstance(events, list) and len(events) == 1, events
    e = events[0]
    assert e['type'] == 'fp_config', e
    assert e['device'] == 'M0', e
    assert e['exp_time'] == 123.0, e            # aligns with the CSV exp_time column
    assert e['detail']['led'] == 'LEDB', e
    assert isinstance(e.get('wall_time'), str) and e['wall_time'], e

    # (c) accumulates across calls (append, not overwrite)
    logEvent(M, 'od_calibration', {'item': 'OD0', 'target': 15438.4})
    with open(fname) as f:
        events = json.load(f)
    assert len(events) == 2, events
    assert events[1]['type'] == 'od_calibration', events
    assert events[1]['detail']['target'] == 15438.4, events

    # (d) atomic write leaves no temp file behind
    assert not os.path.isfile(fname + '.tmp'), 'temp file must be renamed away'

print('PASS: logEvent no-ops when idle, appends a JSON array while running, accumulates across calls, atomic write leaves no temp file')
