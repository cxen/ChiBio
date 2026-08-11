#!/usr/bin/env python3
"""Off-device test for CHIBIO_SIM (chibio_sim.py) -- the no-reactor simulation mode.

The point of the sim mode is that it fakes the *bus*, so the real product code above
it runs: initialiseAll/initialise, the presence scan, the LED V1/V2 auto-detection and
the FP3 remap that hangs off it, and measure_od/measure_fp's real arithmetic. These
tests assert exactly that -- in particular that every field CHIBIO_MOCK_HW leaves at
its raw template value (FP *Record still an int, FP bands still 0, LED version stuck
at 1) is properly populated here, since that gap is the whole reason the mode exists.

    CHIBIO_MOCK_HW=1 python3 test_sim.py
"""
import os
import subprocess
import sys

# Set before importing app: chibio_sim reads its configuration at import time.
os.environ.setdefault('CHIBIO_SIM', '1')
os.environ.setdefault('CHIBIO_SIM_LED_VERSION', '2')
os.environ.setdefault('CHIBIO_SIM_REACTORS', 'M0,M1,M2')
os.environ.setdefault('CHIBIO_SIM_HOURS', '6')

import chibio_sim
from chibio_state import sysData

# CHIBIO_SIM must imply the mock GPIO, or the watchdog would drive real pins.
assert chibio_sim.SIM, "CHIBIO_SIM should be on"
assert chibio_sim.MOCK_HW, "CHIBIO_SIM must imply MOCK_HW (no real GPIO, no watchdog)"

import app  # noqa: E402  -- importing runs _boot() -> chibio_sim.install()

assert app.MOCK_HW, "app must see MOCK_HW via chibio_sim"

ALL = ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']
PRESENT = ['M0', 'M1', 'M2']
ABSENT = [M for M in ALL if M not in PRESENT]

# --- presence comes out of the real scan path, not a hardcoded flag ----------
for M in PRESENT:
    assert sysData[M]['present'] == 1, "%s should be present in sim" % M
for M in ABSENT:
    assert sysData[M]['present'] == 0, "%s has no simulated hardware, must scan absent" % M

# --- the initialise() gap that CHIBIO_MOCK_HW leaves behind is closed --------
for M in PRESENT:
    d = sysData[M]
    for FP in ['FP1', 'FP2', 'FP3']:
        for key in ['BaseRecord', 'Emit1Record', 'Emit2Record']:
            assert isinstance(d[FP][key], list), "%s %s %s must be a list, not %r" % (M, FP, key, d[FP][key])
        assert d[FP]['BaseBand'] == 'CLEAR', "%s %s baseband unset" % (M, FP)
        assert isinstance(d[FP]['Emit1Band'], str) and d[FP]['Emit1Band'].startswith('nm'), \
            "%s %s Emit1Band unset (this is what blanks the GUI dropdown)" % (M, FP)
        assert str(d[FP]['Gain']).startswith('x'), "%s %s gain unset" % (M, FP)
        assert str(d[FP]['LED']).startswith('LED'), "%s %s excitation LED unset" % (M, FP)
    assert isinstance(d['OD']['record'], list), "%s OD record must be a list" % M
    assert d['OD0']['target'] == 65000.0, "%s OD blank not initialised" % M
    assert d['DeviceID'].startswith('SIM-'), "%s device ID must be marked simulated" % M

# --- LED version is pinned, and the FP3 remap follows from it ----------------
for M in PRESENT:
    assert sysData[M]['Version']['LED'] == 2, "%s should report the pinned LED version 2" % M
    assert sysData[M]['FP3']['LED'] == 'LEDH', \
        "%s on V2 must remap FP3 to LEDH (this is real initialise() logic, not a sim shortcut)" % M

# --- synthetic history: every series parallel to time.record -----------------
for M in PRESENT:
    d = sysData[M]
    n = len(d['time']['record'])
    assert n > 0, "%s should have synthetic history" % M
    series = {
        'OD.record': d['OD']['record'],
        'OD.targetrecord': d['OD']['targetrecord'],
        'OD.spreadRecord': d['OD']['spreadRecord'],
        'OD.correctedRecord': d['OD']['correctedRecord'],
        'Thermostat.record': d['Thermostat']['record'],
        'Light.record': d['Light']['record'],
        'GrowthRate.record': d['GrowthRate']['record'],
        'ThermometerInternal.record': d['ThermometerInternal']['record'],
        'ThermometerExternal.record': d['ThermometerExternal']['record'],
        'ThermometerIR.record': d['ThermometerIR']['record'],
    }
    for pump in ['Pump1', 'Pump2', 'Pump3', 'Pump4']:
        series[pump + '.record'] = d[pump]['record']
    for FP in ['FP1', 'FP2', 'FP3']:
        for key in ['BaseRecord', 'Emit1Record', 'Emit2Record']:
            series['%s.%s' % (FP, key)] = d[FP][key]
    for name, values in series.items():
        assert len(values) == n, \
            "%s %s has %d points but time.record has %d (uPlot needs parallel series)" % (M, name, len(values), n)
    # Growth: a logistic culture must actually have grown over the window.
    assert d['OD']['record'][-1] > d['OD']['record'][0] * 2, "%s history should show growth" % M
    # The FP base is a 16-bit ADC count; synthetic history must respect the ceiling.
    for FP in ['FP1', 'FP2', 'FP3']:
        peak = max(d[FP]['BaseRecord'])
        assert peak <= 65535, "%s %s synthetic base %.0f exceeds the ADC ceiling" % (M, FP, peak)
    # ...and the OD blank/raw pair must agree with the OD the history ended on.
    assert abs(d['OD0']['raw'] - chibio_sim._transmission_counts(M, d['OD']['record'][-1])) < 1.0, \
        "%s OD0 raw transmission should match the final history OD" % M
    # runExperiment computes `datetime.now() - startTimeRaw`, so a POSIX float here
    # kills the experiment thread on its first cycle. Pressing Start on a sim with
    # pre-loaded history resumes (cycles != 0), so it uses exactly this value.
    from datetime import datetime as _dt
    assert isinstance(d['Experiment']['startTimeRaw'], _dt), \
        "%s startTimeRaw must be a datetime, got %r" % (M, type(d['Experiment']['startTimeRaw']))
    _dt.now() - d['Experiment']['startTimeRaw']  # must not raise
    assert isinstance(d['Experiment']['startTime'], str), "%s startTime should be the display string" % M

# --- measure_od round-trips the modelled OD through the real calibration -----
# _transmission_counts inverts measure_od's log10/LASERa/LASERb formula, so whatever
# OD the culture model holds must come back out of the real measurement code.
from chibio_measurements import measure_fp, measure_od  # noqa: E402

for M in PRESENT:
    modelled = chibio_sim._state(M)['od']
    measure_od(M)
    recovered = sysData[M]['OD']['current']
    assert abs(recovered - modelled) < 0.02 + 0.02 * modelled, \
        "%s measure_od recovered %.4f from a modelled OD of %.4f" % (M, recovered, modelled)
    assert sysData[M]['OD']['valid'] == 1, "%s OD read should be valid" % M
    assert sysData[M]['OD0']['raw'] > 0, "%s raw transmission should be recorded" % M
    assert sysData[M]['OD0']['dark'] >= 0, "%s dark channel should be recorded" % M

# --- measure_fp produces a real ratio that tracks biomass -------------------
M = PRESENT[0]
sysData[M]['FP1']['ON'] = 1
chibio_sim._state(M)['od'] = 0.2
measure_fp(M)
low = sysData[M]['FP1']['Emit1']
assert sysData[M]['FP1']['valid'] == 1, "a mid-range FP read should be valid"
assert sysData[M]['FP1']['Base'] > 0, "FP base should be a real count"

chibio_sim._state(M)['od'] = 1.2
measure_fp(M)
high = sysData[M]['FP1']['Emit1']
assert high > low, "FP emit/base ratio should rise with biomass (%.4f -> %.4f)" % (low, high)
sysData[M]['FP1']['ON'] = 0

# --- the culture model responds to pumping (turbidostat can close the loop) --
M = PRESENT[0]
state = chibio_sim._state(M)
state['od'] = 1.0
state['last'] = state['last'] - 1800.0  # pretend half an hour passed
sysData[M]['Pump1']['ON'] = 1
sysData[M]['Pump1']['target'] = 1.0
chibio_sim._advance(M)
sysData[M]['Pump1']['ON'] = 0
assert state['od'] < 1.0, "running the input pump must dilute the simulated culture (got %.4f)" % state['od']

# --- the LED version pin actually changes the panel (separate process) -------
# chibio_sim reads its env at import, so version 1 needs a fresh interpreter.
child = subprocess.run(
    [sys.executable, '-c',
     'import app\n'
     'from chibio_state import sysData\n'
     'print(sysData["M0"]["Version"]["LED"], sysData["M0"]["FP3"]["LED"])\n'],
    env=dict(os.environ, CHIBIO_SIM_LED_VERSION='1', CHIBIO_SIM_REACTORS='M0', CHIBIO_SIM_HOURS='0'),
    capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
assert child.returncode == 0, "V1 sim child failed:\n%s" % child.stderr[-2000:]
version, fp3 = child.stdout.strip().splitlines()[-1].split()
assert version == '1', "CHIBIO_SIM_LED_VERSION=1 should present a V1 board, got %s" % version
assert fp3 == 'LEDE', "on V1 FP3 keeps its LEDE excitation, got %s" % fp3

print("PASS: sim mode runs the real init/measurement code over a fake bus "
      "(presence scan, LED version pin + FP3 remap, populated FP fields, "
      "OD round-trip, FP ratio, pump dilution, parallel history series)")
