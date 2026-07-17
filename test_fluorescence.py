#!/usr/bin/env python3
"""Off-device tests for the fluorescence configuration assist:
  A) the Stokes-shift recommendation is pure -- it picks the fluorescence peak and ignores
     excitation scatter; returns None for a non-fluorescent sample.
  B) the scan builds a gain-normalised EEM and recommendation without hardware (get_light and
     the actuation calls are stubbed).

    CHIBIO_MOCK_HW=1 python3 test_fluorescence.py
"""
import os
os.environ['CHIBIO_MOCK_HW'] = '1'

from chibio_fluorescence import recommend_fp_settings, EMISSION_BANDS


def mkrow(wl, **bands):
    row = {'_wl': wl, '_gain': 5, '_power': 0.5}
    for b, _ in EMISSION_BANDS:
        row[b] = 0.0
    row.update(bands)
    return row


# --- A) pure analysis ---
# GFP-like: LEDB (457nm) excitation, strong emission at nm510. The big nm440 count is scatter
# (below the excitation) and MUST be ignored by the Stokes rule.
eem = {
    'LEDA': mkrow(395, nm440=5.0),
    'LEDB': mkrow(457, nm440=99.0, nm510=40.0, nm550=12.0),
    'LEDD': mkrow(523, nm583=3.0),
}
rec = recommend_fp_settings(eem)
assert rec is not None
assert rec['excite'] == 'LEDB', rec
assert rec['emit1'] == 'nm510', "peak must be the Stokes-shifted band, not the nm440 scatter"
assert rec['emit2'] == 'nm550', "second-strongest Stokes-shifted band"
assert rec['base'] == 'CLEAR' and rec['gain'] == 'x5'

# Non-fluorescent: only signal is at/below the excitation -> no recommendation.
assert recommend_fp_settings({'LEDE': mkrow(595, nm550=50.0)}) is None

# --- B) scan flow with stubbed hardware ---
import chibio_state, chibio_optics, app
import chibio_fluorescence as F

M = 'M0'
sd = chibio_state.sysData[M]
sd.setdefault('AS7341', {}).setdefault('current', {})

_state = {'led': None}
app.set_output_on_sync = lambda m, item, v: _state.__setitem__('led', item if int(v) == 1 else None)
app.set_output_target_sync = lambda m, item, v: None
app.addTerminal = lambda m, msg: None

def fake_get_light(m, bands, gain, isteps, autorange=False):
    sd['AS7341']['current']['gain'] = 5  # pretend auto-range settled here
    vals = {b: 10 for b, _ in EMISSION_BANDS}
    if _state['led'] == 'LEDB':            # fluorophore excited by LEDB: scatter@440 + emission@510
        vals['nm440'] = 800; vals['nm510'] = 600; vals['nm550'] = 200
    return [vals.get(b, 0) for b in bands]
chibio_optics.get_light = fake_get_light

F.fluorescence_scan(M, 'quick')
fs = sd['FluorescenceScan']
assert set(fs['matrix']) == {led for led, _ in F.EXCITATION_LEDS}, "EEM must cover every excitation LED"
# gain-normalised: nm510 = 600 / (0.5 * 2**5=16) = 37.5
assert abs(fs['matrix']['LEDB']['nm510'] - 37.5) < 1e-6, fs['matrix']['LEDB']['nm510']
r = fs['recommendation']
assert r['excite'] == 'LEDB' and r['emit1'] == 'nm510', r

print("PASS: Stokes analysis picks the fluorescence peak (ignoring scatter); scan builds a gain-normalised EEM + recommendation")
