#!/usr/bin/env python3
"""Off-device test for the per-experiment metadata sidecar. Runs anywhere the pip
deps are installed (no hardware):

    python3 test_metadata_sidecar.py

Checks (a) the sidecar JSON has the documented structure and values, and (b) its
column_units cover EXACTLY the columns csvData writes -- so the two can't drift.
"""
import csv
import json
import os
import tempfile

import chibio_state
from chibio_control_helpers import csvData, writeExperimentMetadata, _CSV_COLUMN_UNITS

M = 'M0'
sd = chibio_state.sysData[M]


def rec(v):
    return {'record': [0.0, v]}


# --- synthetic state covering what BOTH csvData and the metadata sidecar read ---
sd['time'] = rec(111.0)
sd['OD'] = {'record': [0.0, 0.42], 'targetrecord': [0.0, 0.30], 'device': 'LASER650'}
sd['OD0'] = {'target': 30000.0, 'raw': 29000.0, 'LASERa': 1.1, 'LASERb': 2.2, 'LEDFa': 3.3, 'LEDAa': 4.4}
sd['Thermostat'] = rec(37.5)
sd['Heat'] = {'target': 0.8, 'ON': 1}
sd['ThermometerInternal'] = rec(25.1); sd['ThermometerExternal'] = rec(38.2); sd['ThermometerIR'] = rec(24.9)
sd['Light'] = rec(0.7)
sd['Pump1'] = rec(1.1); sd['Pump2'] = rec(1.2); sd['Pump3'] = rec(1.3); sd['Pump4'] = rec(1.4)
sd['Volume'] = {'target': 20.0}
sd['Stir'] = {'target': 0.9, 'ON': 1}
for i, LED in enumerate(['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV','LASER650']):
    sd[LED] = {'target': 10.0 + i}
sd['UV'] = {'target': 0.6, 'ON': 1}
for FP, on in [('FP1', 1), ('FP2', 0), ('FP3', 1)]:
    sd[FP] = {'ON': on, 'Base': 100.0, 'Emit1': 101.0, 'Emit2': 102.0,
              'LED': 'LEDD', 'Gain': 'x256', 'BaseBand': 'CLEAR', 'Emit1Band': 'nm510', 'Emit2Band': 'nm550'}
sd['Custom'] = {'param1': 1.5, 'param2': 2.5, 'param3': 3.5, 'Status': 4, 'ON': 1}
sd['Zigzag'] = {'target': 0.11, 'ON': 1}
sd['GrowthRate'] = {'current': 0.22}
sd['DeviceID'] = 'CB-TEST-007'
sd['Version'] = {'LED': 2}
sd['Experiment'] = {'startTime': '2026-07-16 12_00_00'}

with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)

    # CSV header = the real column set csvData produces.
    csvData(M)
    with open('2026-07-16 12_00_00_%s_data.csv' % M, newline='') as f:
        csv_columns = next(csv.reader(f))

    writeExperimentMetadata(M)
    with open('2026-07-16 12_00_00_%s_meta.json' % M) as f:
        meta = json.load(f)

# (a) structure + values
assert meta['device'] == 'M0'
assert meta['device_id'] == 'CB-TEST-007'
assert meta['led_hardware_version'] == 2
assert meta['start_time'] == '2026-07-16 12_00_00'
assert meta['integration_steps'] == 255
assert meta['od']['device'] == 'LASER650'
assert meta['od']['gain'] == 1, "OD gain must mirror measure_od's LASER650=1"
assert meta['od']['calibration']['LASERb'] == 2.2, "OD calibration constants must be captured"
assert meta['fluorescence']['FP1']['gain'] == 'x256'
assert meta['fluorescence']['FP2']['on'] == 0
assert isinstance(meta['software_git_hash'], str) and meta['software_git_hash']

# (b) units cover EXACTLY the CSV columns (drift guard)
units_keys = set(_CSV_COLUMN_UNITS)
cols = set(csv_columns)
assert units_keys == cols, "column_units drifted from CSV columns:\n missing units=%s\n extra units=%s" % (
    sorted(cols - units_keys), sorted(units_keys - cols))
assert set(meta['column_units']) == cols

print("PASS: metadata sidecar well-formed; column_units match all %d CSV columns; git=%s" % (
    len(cols), meta['software_git_hash'][:8]))
