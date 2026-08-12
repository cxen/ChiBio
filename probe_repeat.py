#!/usr/bin/env python3
"""Scan-to-scan repeatability of the fluorescence EEM, on whatever is in the reactors.

Single-owner (INVARIANTS 4). Read-mostly: the scan drives its own excitation LEDs and
switches each off; Stir is toggled so each scan sees the same optical state as the
experiment loop (stir off + 5 s settle).

Why: recommend_fp_settings picks the largest Stokes-valid EEM cell. To say anything about
whether a cell is a real signal you need the noise on that cell, and the only honest source
of that is repeated scans of the same unchanged sample. N repeats per reactor.

Usage: python3 probe_repeat.py [N] [outfile.json]
"""
import json
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:5000'
SETTLE_SECONDS = 5
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
    return sysdata()


def stir(M, on):
    if on:
        post('/SetOutputTarget/Stir/%s/0.5' % M)
        time.sleep(0.3)
    post('/SetOutputOn/Stir/%d/%s' % (1 if on else 0, M))
    time.sleep(0.3)


def scan(M):
    post('/FluorescenceScan/%s/quick' % M)
    t0 = time.time()
    while time.time() - t0 < SCAN_TIMEOUT:
        time.sleep(3)
        fs = sysdata().get('FluorescenceScan') or {}
        if fs.get('status') == 'done':
            return fs
    return {'status': 'timeout'}


def od(M):
    post('/MeasureOD/' + M)
    time.sleep(3)
    d = sysdata()
    return {'raw': d['OD0']['raw'], 'spread': d['OD']['spread'], 'valid': d['OD']['valid']}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out = sys.argv[2] if len(sys.argv) > 2 else '/root/chibio-repeat.json'
    d0 = sysdata()
    present = [m for m, v in sorted(d0['presentDevices'].items()) if v]
    res = {'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'repeats': n, 'runs': []}
    t0 = time.time()
    for i in range(n):
        rec = {'i': i, 'eem': {}, 'od': {}}
        for M in present:
            select(M)
            stir(M, True)
            time.sleep(20)          # homogenise before each repeat: same starting state every time
            stir(M, False)
            time.sleep(SETTLE_SECONDS)
            rec['od'][M] = od(M)
            rec['eem'][M] = scan(M)
            stir(M, True)
            print(i, M, rec['od'][M]['raw'], (rec['eem'][M].get('recommendation') or {}).get('signal'))
            sys.stdout.flush()
        res['runs'].append(rec)
    for M in present:
        select(M)
        stir(M, False)
        for item in ('LEDA', 'LEDB', 'LEDC', 'LEDD', 'LEDE', 'LEDF', 'LEDG', 'LEDH',
                     'LEDI', 'UV', 'LASER650', 'Heat'):
            post('/SetOutputOn/%s/0/%s' % (item, M))
            time.sleep(0.05)
    res['seconds'] = round(time.time() - t0, 1)
    with open(out, 'w') as f:
        json.dump(res, f, indent=1)
    print('wrote', out, 'in', res['seconds'], 's')


if __name__ == '__main__':
    main()
