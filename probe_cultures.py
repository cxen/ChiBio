#!/usr/bin/env python3
"""One-shot bench probe of whatever is currently in the reactors.

Single-owner (INVARIANTS 4): run this and nothing else against the server.
Read-mostly -- the only actuation is Stir (to homogenise before reading) and the
excitation LEDs the fluorescence scan drives and switches off itself. It never
writes a calibration, never starts an experiment, and leaves every output off.

Phases, per present reactor:
  A settled  -- OD as the vials sit (no stir): sedimentation state
  B mixed    -- stir 2 min, stir off, 5 s settle, 3x OD: the state runExperiment measures in
  C EEM      -- quick fluorescence scan: excitation x emission matrix + what the
                recommender picks. With WT/sterile in every vial this is a
                known-answer test: any "recommendation" is autofluorescence or leak.

Usage: python3 probe_cultures.py [outfile.json]
"""
import json
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:5000'
MIX_SECONDS = 120
SETTLE_SECONDS = 5
OD_REPLICATES = 3
OD_SPACING = 8          # >= the 5 s spacing rule; reads are mutex-safe now but settling is physical
SCAN_TIMEOUT = 300


def post(path):
    req = urllib.request.Request(BASE + path, data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def sysdata():
    with urllib.request.urlopen(BASE + '/getSysdata/', timeout=60) as r:
        return json.loads(r.read().decode())


def select(M):
    post('/changeDevice/' + M)
    time.sleep(0.5)
    d = sysdata()
    if d.get('DeviceID') is None:
        raise RuntimeError('no sysdata for ' + M)
    return d


def wait_idle(M, what='OD', timeout=60):
    # measurement routes are fire-and-forget; wait for the in-flight read to clear
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = sysdata()
        if not d[what].get('Measuring'):
            return d
        time.sleep(0.5)
    return sysdata()


def read_od(M):
    post('/MeasureOD/' + M)
    time.sleep(2.0)
    d = wait_idle(M)
    od = d['OD']
    return {'raw': d['OD0']['raw'], 'dark': d['OD0']['dark'],
            'rawCorrected': d['OD0']['rawCorrected'], 'blank_target': d['OD0']['target'],
            'current': od['current'], 'corrected': od['corrected'],
            'spread': od['spread'], 'valid': od['valid']}


def read_temps(M):
    out = {}
    for which in ('Internal', 'External', 'IR'):
        post('/MeasureTemp/%s/%s' % (which, M))
        time.sleep(1.5)
    d = sysdata()
    for which in ('Internal', 'External', 'IR'):
        out[which] = d['Thermometer' + which]['current']
    return out


def stir(M, on, target=0.5):
    if on:
        post('/SetOutputTarget/Stir/%s/%s' % (M, target))
        time.sleep(0.3)
    post('/SetOutputOn/Stir/%d/%s' % (1 if on else 0, M))
    time.sleep(0.3)


def scan(M, mode='quick'):
    post('/FluorescenceScan/%s/%s' % (M, mode))
    t0 = time.time()
    while time.time() - t0 < SCAN_TIMEOUT:
        time.sleep(3)
        d = sysdata()
        fs = d.get('FluorescenceScan') or {}
        if fs.get('status') == 'done':
            fs['_seconds'] = round(time.time() - t0, 1)
            return fs
    return {'status': 'timeout'}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/root/chibio-probe.json'
    t_start = time.time()
    d0 = sysdata()
    present = [m for m, v in sorted(d0['presentDevices'].items()) if v]
    print('present:', present)

    result = {'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'present': present,
              'settled': {}, 'mixed': {}, 'temps': {}, 'eem': {}, 'led_version': {}}

    # --- A: settled ---
    for M in present:
        select(M)
        result['settled'][M] = read_od(M)
        result['led_version'][M] = sysdata()['Version']['LED']
        print('A', M, result['settled'][M])

    # --- B: mixed ---
    for M in present:
        select(M)
        stir(M, True)
    print('mixing %d s' % MIX_SECONDS)
    time.sleep(MIX_SECONDS)

    for M in present:
        select(M)
        stir(M, False)
        time.sleep(SETTLE_SECONDS)
        reps = []
        for i in range(OD_REPLICATES):
            reps.append(read_od(M))
            if i < OD_REPLICATES - 1:
                time.sleep(OD_SPACING)
        result['mixed'][M] = reps
        result['temps'][M] = read_temps(M)
        print('B', M, [r['raw'] for r in reps], result['temps'][M])
        stir(M, True)

    # --- C: EEM, measured in the same optical state the experiment loop uses ---
    for M in present:
        select(M)
        stir(M, False)
        time.sleep(SETTLE_SECONDS)
        result['eem'][M] = scan(M, 'quick')
        rec = (result['eem'][M] or {}).get('recommendation')
        print('C', M, result['eem'][M].get('status'), rec)
        stir(M, True)

    # --- cleanup: everything off ---
    for M in present:
        select(M)
        stir(M, False)
        for item in ('LEDA', 'LEDB', 'LEDC', 'LEDD', 'LEDE', 'LEDF', 'LEDG', 'LEDH',
                     'LEDI', 'UV', 'LASER650', 'Heat'):
            post('/SetOutputOn/%s/0/%s' % (item, M))
            time.sleep(0.05)

    result['seconds'] = round(time.time() - t_start, 1)
    with open(out, 'w') as f:
        json.dump(result, f, indent=1)
    print('wrote', out, 'in', result['seconds'], 's')


if __name__ == '__main__':
    main()
