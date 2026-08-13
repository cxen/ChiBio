#!/usr/bin/env python3
"""Device test for timed dosing schedules, on a live reactor.

Deliberately drives LEDB at low power and the (inactive) thermostat setpoint rather than a pump:
that exercises the whole path -- validation, the background thread, the experiment clock, stage
transitions, the events sidecar and the CSV column, including real I2C writes through
set_output_target_sync -- without pumping anything into a vial.

Runs a real experiment on the target reactor for ~3 min so the schedule has an experiment clock
to measure against. With OD control off, a cycle only measures and logs; it does not pump.

Single-owner (INVARIANTS 4). Usage: python3 probe_schedule.py [M2]
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:5000'
M = sys.argv[1] if len(sys.argv) > 1 else 'M2'


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b''
    req = urllib.request.Request(BASE + path, data=data, method='POST')
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, ''
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def sysdata():
    with urllib.request.urlopen(BASE + '/getSysdata/', timeout=60) as r:
        return json.loads(r.read().decode())


post('/changeDevice/' + M)
time.sleep(0.5)
print('reactor', M)

# --- 1. the server refuses what it should, with a message that names the row ---
print('\n== validation, on the device ==')
for label, stages in [
    ('unknown channel', [{'at_h': 0, 'item': 'Teleporter', 'target': 1}]),
    ('out of range', [{'at_h': 0, 'item': 'Pump3', 'target': 5.0}]),
    ('negative hour', [{'at_h': -2, 'item': 'Pump3', 'target': 0.01}]),
    ('ramped stir', [{'at_h': 0, 'item': 'Stir', 'target': 0.2},
                     {'at_h': 1, 'item': 'Stir', 'target': 0.8, 'ramp': 1}]),
]:
    code, msg = post('/SetSchedule/' + M, {'stages': stages})
    print('  %-16s HTTP %s  %s' % (label, code, msg.strip()[:110]))

# --- 2. a real schedule: an LED step at ~18 s and off at ~50 s, plus a ramped setpoint ---
stages = [
    {'at_h': 0.0,    'item': 'LEDB', 'target': 0.0},
    {'at_h': 0.005,  'item': 'LEDB', 'target': 0.30},          # ~18 s
    {'at_h': 0.014,  'item': 'LEDB', 'target': 0.0},           # ~50 s
    {'at_h': 0.0,    'item': 'ThermostatTarget', 'target': 30.0},
    {'at_h': 0.014,  'item': 'ThermostatTarget', 'target': 34.0, 'ramp': 1},
]
code, msg = post('/SetSchedule/' + M, {'stages': stages})
print('\n== accepted schedule: HTTP %s %s ==' % (code, msg))
assert code == 204, msg

# --- 3. run it against a real experiment clock ---
print('\n== starting an experiment (no OD control -> measures and logs, does not pump) ==')
print('  Experiment start:', post('/Experiment/1/' + M)[0])
time.sleep(3)
print('  Schedule start:  ', post('/ScheduleOnOff/1/' + M))

print('\n  t(s)  sched status                 applied  LEDB target/ON   Thermostat target')
t0 = time.time()
seen_on = False
seen_ramp = set()
while time.time() - t0 < 200:
    d = sysdata()
    sc = d['Schedule']
    led, th = d['LEDB'], d['Thermostat']['target']
    print('  %4.0f  %-28s %5d    %.3f / %d        %.3f'
          % (time.time() - t0, sc['status'][:28], sc['applied'], led['target'], led['ON'], th))
    if led['ON'] and led['target'] > 0.2:
        seen_on = True
    seen_ramp.add(round(th, 2))
    sys.stdout.flush()
    time.sleep(10)

print('\n== stopping ==')
print('  Schedule stop:  ', post('/ScheduleOnOff/0/' + M))
print('  Experiment stop:', post('/Experiment/0/' + M)[0])
time.sleep(2)
for item in ('LEDB', 'Stir', 'Heat'):
    post('/SetOutputOn/%s/0/%s' % (item, M))
    time.sleep(0.1)

d = sysdata()
print('\n== result ==')
print('  LED was driven ON at the scheduled target:', seen_on)
print('  distinct thermostat setpoints seen (a ramp gives several):', sorted(seen_ramp))
print('  outputs left on:', [k for k in ('LEDB', 'Stir', 'Heat', 'LASER650') if d[k]['ON']] or 'none')
print('  schedule status now:', d['Schedule']['status'], '| ON =', d['Schedule']['ON'])
