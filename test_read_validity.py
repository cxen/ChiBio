#!/usr/bin/env python3
"""Off-device fault-injection test for the AS7341 read-validity path (the "no fake
fallback values" item). The failure branch can't be exercised on live hardware, so
this monkeypatches as7341_read to fail and checks:

  - a double failure sets current['valid']=0 and does NOT fabricate ADC0=1 / rest=0
    (the old behaviour) -- last-known ADC values are preserved,
  - a success sets current['valid']=1,
  - csvData records NaN for od_measured when OD['valid']==0, and a real value when valid,
  - csvData records NaN for an active FP's cells when that FP['valid']==0.

Run (needs CHIBIO_MOCK_HW so chibio_hardware imports without Adafruit_BBIO):

    CHIBIO_MOCK_HW=1 python3 test_read_validity.py
"""
import csv
import math
import os
import tempfile

assert os.environ.get('CHIBIO_MOCK_HW'), "run with CHIBIO_MOCK_HW=1"

import chibio_state
import chibio_optics
from chibio_optics import get_light
from chibio_control_helpers import csvData

M = 'M0'
sd = chibio_state.sysData[M]

# last-known ADC values that must survive a failed read (never overwritten with fakes)
LAST_KNOWN = {'ADC0': 5000, 'ADC1': 4000, 'ADC2': 3000, 'ADC3': 2000, 'ADC4': 1000, 'ADC5': 500}
sd['AS7341']['current'].update(LAST_KNOWN)
sd['AS7341']['current']['valid'] = 1


# --- 1. double failure -> valid=0, values preserved (no fabricated ADC0=1) ---
def boom(*a, **k):
    raise RuntimeError("injected I2C failure")

chibio_optics.as7341_read = boom
out = get_light(M, ['CLEAR'], 1, 255)
assert sd['AS7341']['current']['valid'] == 0, "failed read must set valid=0"
assert sd['AS7341']['current']['ADC0'] == 5000, "must keep last-known ADC0, not fabricate 1"
for k, v in LAST_KNOWN.items():
    assert sd['AS7341']['current'][k] == v, "%s was overwritten on failure" % k


# --- 2. success -> valid=1 ---
def ok(Mx, Gain, ISteps, reset):
    sd['AS7341']['current']['ADC0'] = 12345  # a fresh good read

chibio_optics.as7341_read = ok
get_light(M, ['CLEAR'], 1, 255)
assert sd['AS7341']['current']['valid'] == 1, "successful read must set valid=1"
assert sd['AS7341']['current']['ADC0'] == 12345


# --- helpers to run csvData and read back one data row ---
def write_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        csvData(M)
        with open('exp_%s_data.csv' % M, newline='') as f:
            rows = list(csv.reader(f))
    return dict(zip(rows[0], rows[1]))


# minimal state csvData needs
sd['time'] = {'record': [0.0, 1.0]}
sd['OD'] = {'record': [0.0, 0.42], 'targetrecord': [0.0, 0.3], 'valid': 1}
sd['OD0'] = {'target': 30000.0}
sd['Thermostat'] = {'record': [0.0, 37.0]}
sd['Heat'] = {'target': 0.0, 'ON': 0}
for t in ('ThermometerInternal', 'ThermometerExternal', 'ThermometerIR'):
    sd[t] = {'record': [0.0, 25.0]}
sd['Light'] = {'record': [0.0, 0.0]}
for p in ('Pump1', 'Pump2', 'Pump3', 'Pump4'):
    sd[p] = {'record': [0.0, 0.0]}
sd['Volume'] = {'target': 20.0}
sd['Stir'] = {'target': 0.0, 'ON': 0}
for LED in ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV','LASER650']:
    sd[LED] = {'target': 0.0}
sd['UV'] = {'target': 0.0, 'ON': 0}
for FP in ('FP1', 'FP2', 'FP3'):
    sd[FP] = {'ON': 1, 'Base': 100.0, 'Emit1': 1.1, 'Emit2': 1.2, 'valid': 1}
sd['Custom'] = {'param1': 0.0, 'param2': 0.0, 'param3': 0.0, 'Status': 0, 'ON': 0}
sd['Zigzag'] = {'target': 0.0, 'ON': 0}
sd['GrowthRate'] = {'current': 0.0}
sd['Experiment'] = {'startTime': 'exp'}

# --- 3. OD valid -> real value; OD invalid -> NaN ---
row = write_and_read()
assert row['od_measured'] == '0.42', "valid OD should log the real value, got %r" % row['od_measured']
assert row['FP1_base'] == '100.0'

sd['OD']['valid'] = 0
sd['FP2']['valid'] = 0  # one active FP fails
row = write_and_read()
assert math.isnan(float(row['od_measured'])), "invalid OD must be NaN, got %r" % row['od_measured']
assert math.isnan(float(row['FP2_base'])), "invalid FP2 base must be NaN"
assert math.isnan(float(row['FP2_emit1'])), "invalid FP2 emit1 must be NaN"
assert row['FP1_base'] == '100.0', "FP1 still valid -> real value"

print("PASS: failed reads set valid=0 without fabricating values; csvData records NaN only for the failed channels")
