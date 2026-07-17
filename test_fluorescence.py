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
sd['Version'] = {'LED': 2}  # V2 board -> LEDB/C/D/I/H/F excitation set

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
assert set(fs['matrix']) == {led for led, _ in F.excitation_leds(M)}, "EEM must cover every V2 excitation LED"
# gain-normalised: nm510 = 600 / (0.5 * 2**5=16) = 37.5
assert abs(fs['matrix']['LEDB']['nm510'] - 37.5) < 1e-6, fs['matrix']['LEDB']['nm510']
r = fs['recommendation']
assert r['excite'] == 'LEDB' and r['emit1'] == 'nm510', r

# --- C) FP3's default excitation must be drivable on the board's LED version ---
# FP3 defaults to LEDE (595nm), which only exists on V1. Driving an absent LED is a silent
# no-op, so on a V2 board FP3 excited nothing while still logging the emit/base ratio as a
# valid reading (and its Excite dropdown rendered blank -- no LEDE in the V2 option list).
# app.initialise() remaps it to LEDH; this asserts LEDH is the right analogue, not an arbitrary
# pick. That initialise() actually applies the remap is a hardware path -- verified on device.
sd['Version'] = {'LED': 1}
v1 = dict(F.excitation_leds(M))
sd['Version'] = {'LED': 2}
v2 = dict(F.excitation_leds(M))

assert v1['LEDE'] == 595
assert 'LEDE' not in v2, "LEDE is V1-only; if it gains a V2 channel the remap is obsolete"
assert 'LEDH' in v2, "the remap target must be a real V2 excitation LED"
# LEDH (600nm) is the nearest V2 channel to LEDE's 595nm -- it takes LEDE's slot in the set.
assert min(v2, key=lambda led: abs(v2[led] - v1['LEDE'])) == 'LEDH', v2
# ...and it must keep a real Stokes shift to FP3's default nm620/nm670 emission bands, or the
# "excitation scatter, not fluorescence" rule would reject everything FP3 reads.
bands = dict(EMISSION_BANDS)
for emit in ('nm620', 'nm670'):
    assert bands[emit] - v2['LEDH'] >= F.STOKES_MIN_SHIFT, (emit, bands[emit], v2['LEDH'])

print("PASS: Stokes analysis picks the fluorescence peak (ignoring scatter); scan builds a gain-normalised EEM + recommendation; FP3's V2 excitation remap (LEDE->LEDH) is the nearest valid channel and keeps its Stokes shift")
