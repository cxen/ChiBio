#!/usr/bin/env python3
"""Prove the csv.DictWriter refactor of csvData() writes a byte-identical header
and row to the old parallel-lists implementation. Runs off-device (no hardware):

    python3 test_csv_equivalence.py

Populates a synthetic sysData['M0'] with a distinct value per source field (so a
mis-mapped column is caught), computes the expected header+row with the OLD
algorithm inline, runs the new csvData(), and diffs the resulting CSV.
"""
import csv
import os
import tempfile

import chibio_state
from chibio_control_helpers import csvData

M = 'M0'
sd = chibio_state.sysData[M]


def rec(v):
    # csvData reads record lists via [-1]; give a 2-element list so [-1] is the value.
    return {'record': [0.0, v]}


# --- synthetic device state: one unique number per field csvData reads ---
sd['time'] = rec(111.0)
sd['OD'] = {'record': [0.0, 0.42], 'targetrecord': [0.0, 0.30]}
sd['OD0'] = {'target': 0.05, 'raw': 29000.0, 'dark': 100.0, 'rawCorrected': 28900.0}
sd['Thermostat'] = rec(37.5)
sd['Heat'] = {'target': 0.8, 'ON': 1}
sd['ThermometerInternal'] = rec(25.1)
sd['ThermometerExternal'] = rec(38.2)
sd['ThermometerIR'] = rec(24.9)
sd['Light'] = rec(0.7)
sd['Pump1'] = rec(1.1); sd['Pump2'] = rec(1.2); sd['Pump3'] = rec(1.3); sd['Pump4'] = rec(1.4)
sd['Volume'] = {'target': 20.0}
sd['Stir'] = {'target': 0.9, 'ON': 1}
for i, LED in enumerate(['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV','LASER650']):
    sd[LED] = {'target': 10.0 + i}
sd['UV'] = {'target': 0.6, 'ON': 1}
sd['FP1'] = {'ON': 1, 'Base': 100.0, 'Emit1': 101.0, 'Emit2': 102.0}
sd['FP2'] = {'ON': 0, 'Base': 200.0, 'Emit1': 201.0, 'Emit2': 202.0}  # OFF -> zeros
sd['FP3'] = {'ON': 1, 'Base': 300.0, 'Emit1': 301.0, 'Emit2': 302.0}
sd['Custom'] = {'param1': 1.5, 'param2': 2.5, 'param3': 3.5, 'Status': 4, 'ON': 1}
sd['Zigzag'] = {'target': 0.11, 'ON': 1}
sd['GrowthRate'] = {'current': 0.22}


# --- expected header + row via the OLD algorithm (verbatim from pre-refactor) ---
exp_fieldnames = ['exp_time','od_measured','od_setpoint','od_zero_setpoint','thermostat_setpoint','heating_rate',
                  'internal_air_temp','external_air_temp','media_temp','opt_gen_act_int','pump_1_rate','pump_2_rate',
                  'pump_3_rate','pump_4_rate','media_vol','stirring_rate','LED_395nm_setpoint','LED_457nm_setpoint',
                  'LED_500nm_setpoint','LED_523nm_setpoint','LED_595nm_setpoint','LED_623nm_setpoint',
                  'LED_6500K_setpoint','LED_600nm_setpoint','LED_550nm_setpoint','LED_White_setpoint','laser_setpoint',
                  'LED_UV_int','FP1_base','FP1_emit1','FP1_emit2','FP2_base','FP2_emit1','FP2_emit2','FP3_base',
                  'FP3_emit1','FP3_emit2','custom_prog_param1','custom_prog_param2','custom_prog_param3',
                  'custom_prog_status','zigzag_target','growth_rate']

exp_row=[sd['time']['record'][-1], sd['OD']['record'][-1], sd['OD']['targetrecord'][-1], sd['OD0']['target'],
    sd['Thermostat']['record'][-1], sd['Heat']['target']*float(sd['Heat']['ON']),
    sd['ThermometerInternal']['record'][-1], sd['ThermometerExternal']['record'][-1], sd['ThermometerIR']['record'][-1],
    sd['Light']['record'][-1], sd['Pump1']['record'][-1], sd['Pump2']['record'][-1], sd['Pump3']['record'][-1],
    sd['Pump4']['record'][-1], sd['Volume']['target'], sd['Stir']['target']*sd['Stir']['ON'],]
for LED in ['LEDA','LEDB','LEDC','LEDD','LEDE','LEDF','LEDG','LEDH','LEDI','LEDV','LASER650']:
    exp_row=exp_row+[sd[LED]['target']]
exp_row=exp_row+[sd['UV']['target']*sd['UV']['ON']]
for FP in ['FP1','FP2','FP3']:
    if sd[FP]['ON']==1:
        exp_row=exp_row+[sd[FP]['Base'], sd[FP]['Emit1'], sd[FP]['Emit2']]
    else:
        exp_row=exp_row+[0.0, 0.0, 0.0]
exp_row=exp_row+[sd['Custom']['param1']*float(sd['Custom']['ON']), sd['Custom']['param2']*float(sd['Custom']['ON']),
    sd['Custom']['param3']*float(sd['Custom']['ON']), sd['Custom']['Status']*float(sd['Custom']['ON']),
    sd['Zigzag']['target']*float(sd['Zigzag']['ON']), sd['GrowthRate']['current']*sd['Zigzag']['ON']]


# --- run the NEW csvData twice (fresh file gets header; second call appends only) ---
with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)
    sd['Experiment'] = {'startTime': 'exp'}
    fname = 'exp_%s_data.csv' % M
    csvData(M)
    csvData(M)  # second row, no new header

    with open(fname, newline='') as f:
        rows = list(csv.reader(f))

# The DictWriter refactor + dark-transmission columns must leave EVERY original
# column's value unchanged; new columns (od_transmission_*) may be added.
assert len(rows) == 3, "expected header + 2 data rows, got %d rows" % len(rows)
new = dict(zip(rows[0], rows[1]))
expected = dict(zip(exp_fieldnames, [str(v) for v in exp_row]))
for name in exp_fieldnames:
    assert name in new, "original column %r disappeared" % name
    assert new[name] == expected[name], "column %r changed: new=%r old=%r" % (name, new[name], expected[name])
assert rows[2] == rows[1], "second appended row should match the first"

added = [c for c in rows[0] if c not in exp_fieldnames]
assert set(added) == {'od_transmission_raw', 'od_transmission_dark', 'od_transmission_corrected',
                      'FP1_gain_used', 'FP2_gain_used', 'FP3_gain_used'}, \
    "unexpected column changes: %s" % added
print("PASS: all %d original columns unchanged; added %d new columns (dark-transmission + FP gain)" % (
    len(exp_fieldnames), len(added)))
