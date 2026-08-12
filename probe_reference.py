#!/usr/bin/env python3
"""Known-answer test of the matched non-fluorescent reference, on live cultures.

Every vial currently holds non-fluorescent material -- WT E. coli in M0/M1/M3, sterile medium
in M2 -- so the true answer for every reactor is "no fluorophore". Before this change the assist
answered LEDI(550)->nm583 on all four, sterile blank included. This drives the real route on the
real hardware and checks what it now says.

Cases:
  1 unreferenced      M3 scanned cold           -> expect the old false positive, labelled unverified
  2 matched WT ref    M0 referenced against M3  -> expect NO recommendation (the true answer)
  3 sterile ref       M1 referenced against M2  -> a 17x density mismatch: expect either no
                                                   recommendation or one carrying the scale warning
  4 cleared           reference removed from M0 -> back to the unreferenced answer

Single-owner (INVARIANTS 4). Read-mostly; the scan drives and switches off its own LEDs.
"""
import json
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:5000'


def post(path):
    req = urllib.request.Request(BASE + path, data=b'', method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def sysdata():
    with urllib.request.urlopen(BASE + '/getSysdata/', timeout=60) as r:
        return json.loads(r.read().decode())


def select(M):
    post('/changeDevice/' + M)
    time.sleep(0.5)


def stir(M, on):
    if on:
        post('/SetOutputTarget/Stir/%s/0.5' % M)
        time.sleep(0.3)
    post('/SetOutputOn/Stir/%d/%s' % (1 if on else 0, M))
    time.sleep(0.3)


def scan(M):
    select(M)
    stir(M, True); time.sleep(20); stir(M, False); time.sleep(5)
    post('/FluorescenceScan/%s/quick' % M)
    t0 = time.time()
    while time.time() - t0 < 300:
        time.sleep(3)
        fs = sysdata().get('FluorescenceScan') or {}
        if fs.get('status') == 'done':
            stir(M, True)
            return fs
    stir(M, True)
    return {'status': 'timeout'}


def show(tag, M, fs):
    r = fs.get('recommendation')
    print('--- %s (%s) ---' % (tag, M))
    print('    referenced=%s from=%s scale=%s' % (fs.get('referenced'), fs.get('reference_from'),
                                                  fs.get('reference_scale')))
    if r is None:
        print('    RECOMMENDATION: none')
    else:
        print('    RECOMMENDATION: %s(%s) -> %s/%s  signal %s  confidence %s'
              % (r['excite'], r['excite_nm'], r['emit1'], r['emit2'], r['signal'], r.get('confidence')))
        if r.get('signal_over_background') is not None:
            print('    signal/background %s  (background %s)' % (r['signal_over_background'], r.get('background')))
        if r.get('warning'):
            print('    warning: ' + r['warning'][:150])
    sys.stdout.flush()
    return r


out = {}
print('== case 1: no reference (the behaviour being replaced) ==')
fs3 = scan('M3')
out['1_unreferenced_M3'] = show('unreferenced', 'M3', fs3)

print('\n== case 2: M0 referenced against M3 -- both WT, near-identical density ==')
select('M0')
code = post('/SetFluorescenceReference/M0/M3')
print('    SetFluorescenceReference/M0/M3 -> HTTP %s' % code)
fs0 = scan('M0')
out['2_referenced_M0_vs_M3'] = show('matched WT reference', 'M0', fs0)

print('\n== case 3: M1 referenced against M2 -- sterile medium, ~17x density mismatch ==')
fs2 = scan('M2')
show('sterile blank, unreferenced', 'M2', fs2)
select('M1')
code = post('/SetFluorescenceReference/M1/M2')
print('    SetFluorescenceReference/M1/M2 -> HTTP %s' % code)
fs1 = scan('M1')
out['3_referenced_M1_vs_M2'] = show('sterile reference', 'M1', fs1)

print('\n== case 4: reference cleared on M0 ==')
select('M0')
print('    clear -> HTTP %s' % post('/SetFluorescenceReference/M0/clear'))
fs0b = scan('M0')
out['4_cleared_M0'] = show('after clearing', 'M0', fs0b)

print('\n== case 5: a source with no scan of its own must be refused ==')
print('    SetFluorescenceReference/M0/M9 -> HTTP %s (expect 409/404, not 204)'
      % post('/SetFluorescenceReference/M0/M9'))

for M in ('M0', 'M1', 'M2', 'M3'):
    select(M)
    stir(M, False)
    for item in ('LEDB', 'LEDC', 'LEDD', 'LEDF', 'LEDH', 'LEDI', 'UV', 'LASER650', 'Heat'):
        post('/SetOutputOn/%s/0/%s' % (item, M))
        time.sleep(0.05)
with open('/root/chibio-reference-test.json', 'w') as f:
    json.dump(out, f, indent=1)
print('\ndone')
