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


# --- D) a dead read (valid=0) must not be recommended, even if its stale counts look strongest ---
eem_bad = {
    'LEDB': mkrow(457, nm510=999.0),   # looks like a huge peak...
    'LEDD': mkrow(523, nm583=40.0),
}
eem_bad['LEDB']['_valid'] = 0          # ...but it was a dropout -> must be skipped
eem_bad['LEDD']['_valid'] = 1
r = recommend_fp_settings(eem_bad)
assert r is not None and r['excite'] == 'LEDD', ('must skip the invalid LEDB row', r)
only_bad = {'LEDB': mkrow(457, nm510=999.0)}; only_bad['LEDB']['_valid'] = 0
assert recommend_fp_settings(only_bad) is None, 'no valid Stokes signal -> recommend nothing'
# rows without a _valid key (older/pure-analysis callers) are treated as valid, so A) still holds.
assert recommend_fp_settings({'LEDB': mkrow(457, nm510=50.0)}) is not None

# --- E) the scan retries a transient dropout instead of baking the bad read into the EEM ---
_calls = {'n': 0}
def flaky_get_light(m, bands, gain, isteps, autorange=False):
    _calls['n'] += 1
    sd['AS7341']['current']['gain'] = 5
    sd['AS7341']['current']['valid'] = 0 if _calls['n'] <= 1 else 1  # only the very first read drops out
    return [10 for _ in bands]
chibio_optics.get_light = flaky_get_light
F.fluorescence_scan(M, 'quick')
matrix = sd['FluorescenceScan']['matrix']
assert all(row['_valid'] == 1 for row in matrix.values()), matrix   # dropout was retried away
assert _calls['n'] > 2 * len(F.excitation_leds(M)), 'a retry must have added at least one extra read'

print("PASS: dead reads (valid=0) are skipped by the recommender; the scan retries a transient dropout and every EEM row it keeps is valid")

# --- F) matched non-fluorescent reference subtraction (the real-rig failure mode) ---
# Built from the four EEMs measured on the rig 2026-08-13, when every reactor held
# non-fluorescent material: three WT cultures (M0/M3 at one density, M1 ~1.8x denser) and a
# sterile-medium blank (M2). The recommender handed ALL FOUR the same confident
# LEDI(550)->nm583/nm620 pick, with the "signal" tracking turbidity (37.7 / 269.6 / 275.9 /
# 516.2). Those are four true negatives, so any recommendation on them is a false positive.
def rig_eem(scale):
    # LEDI row as measured on M0, scaled -- the 550nm LED is 105nm FWHM, so its own red tail
    # lands squarely in nm583/nm620 and dominates every non-fluorescent sample.
    return {
        'LEDB': mkrow(457, nm410=145.3*scale, nm440=1152.1*scale, nm470=101.7*scale,
                      nm510=30.8*scale, nm583=39.6*scale, nm620=40.6*scale),
        'LEDD': mkrow(523, nm470=151.2*scale, nm510=722.6*scale, nm550=63.3*scale,
                      nm583=18.8*scale, nm620=17.4*scale),
        'LEDI': mkrow(550, nm510=299.5*scale, nm550=166.7*scale, nm583=269.6*scale,
                      nm620=175.2*scale, nm670=54.2*scale),
        'LEDH': mkrow(600, nm550=77.6*scale, nm583=272.3*scale, nm620=212.2*scale, nm670=53.2*scale),
        'LEDF': mkrow(623, nm583=274.7*scale, nm620=948.8*scale, nm670=16.2*scale),
    }

wt = rig_eem(1.0)
wt_denser = rig_eem(1.8)

# Without a reference the pick is the measured false positive, and it must say so.
r = recommend_fp_settings(wt)
assert r is not None and (r['excite'], r['emit1']) == ('LEDI', 'nm583'), r
assert r['confidence'] == 'unreferenced', r
assert 'warning' in r and 'sterile' in r['warning'].lower(), r

# With a matched non-fluorescent reference, the true answer (no fluorophore) is returned.
assert recommend_fp_settings(wt, reference=rig_eem(1.0)) is None, 'WT vs identical WT'
assert recommend_fp_settings(wt_denser, reference=wt) is None, 'WT vs WT across a 1.8x density gap'
assert recommend_fp_settings(wt, reference=wt_denser) is None, 'and in the other direction'

# The scale is fitted, not assumed: a 1.8x denser sample must recover ~1.8.
from chibio_fluorescence import subtract_reference
resid, scale, background = subtract_reference(wt_denser, wt)
assert 1.7 < scale < 1.9, scale
assert abs(resid['LEDI']['nm583']) < 0.25 * background['LEDI']['nm583'], resid['LEDI']

# A real fluorophore must survive the subtraction. GFP on a V2 board is read LEDB(457)->nm510
# (no ~488nm channel exists -- see the assist's V2 caveat), so put the emission there, at 3x that
# cell's background: comfortably over the 25% residual threshold.
gfp = rig_eem(1.0)
gfp['LEDB']['nm510'] += 3.0 * wt['LEDB']['nm510']
r = recommend_fp_settings(gfp, reference=wt)
assert r is not None, 'a real FP must not be subtracted away'
assert (r['excite'], r['emit1']) == ('LEDB', 'nm510'), r
assert r['confidence'] == 'referenced' and r['reference_scale'] is not None, r
assert r['signal_over_background'] > 2.0, r

# ...and one at 10% of background -- inside the measured WT-vs-WT residual floor -- must NOT be
# reported, because on real data that size of difference appears between two identical WT vials.
faint = rig_eem(1.0)
faint['LEDB']['nm510'] += 0.10 * wt['LEDB']['nm510']
assert recommend_fp_settings(faint, reference=wt) is None, 'below the measured residual floor'

# A reference at a wildly different density still works but must flag itself.
r = recommend_fp_settings(rig_eem(5.0), reference=gfp)
if r is not None:
    assert 'warning' in r, r

print("PASS: reference subtraction returns the true negative on four measured non-fluorescent "
      "EEMs, recovers the density scale, keeps a real FP, and drops one under the measured floor")

# --- G) the reference is state, wired through the route helper ---
from chibio_state import sysData, sysDevices
import chibio_fluorescence as FL

sysData['M1']['FluorescenceScan'] = {'status': 'done', 'matrix': rig_eem(1.0)}
sysData['M1']['present'] = 1

# A device with no completed scan cannot be adopted as a reference.
sysData['M2']['FluorescenceScan'] = {'status': '', 'matrix': {}}
assert FL.set_fluorescence_reference('M0', 'M2') is False, 'no scan -> refuse, do not store an empty EEM'
assert FL.reference_matrix('M0') is None

assert FL.set_fluorescence_reference('M0', 'M1') is True
assert sysData['M0']['FluorescenceReference']['from'] == 'M1'
# The EEM itself must NOT be in sysData: that dict is jsonified to the browser on every poll.
assert 'matrix' not in sysData['M0']['FluorescenceReference'], 'bulk EEM must not ride the poll payload'
assert FL.reference_matrix('M0') is not None and len(FL.reference_matrix('M0')) == 5
# ...and it must be a copy, so a later scan on M1 cannot silently mutate M0's reference.
sysData['M1']['FluorescenceScan']['matrix']['LEDI']['nm583'] = 99999.0
assert FL.reference_matrix('M0')['LEDI']['nm583'] != 99999.0, 'reference must be an independent copy'

assert FL.set_fluorescence_reference('M0', 'clear') is True
assert FL.reference_matrix('M0') is None and sysData['M0']['FluorescenceReference']['from'] == ''

print("PASS: reference set/clear refuses an unscanned source, stores the EEM outside the polled "
      "payload, and keeps an independent copy")
