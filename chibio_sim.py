"""CHIBIO_SIM=1 -- run the whole Chi.Bio UI with no reactors attached.

This is NOT the same thing as CHIBIO_MOCK_HW=1, and the difference matters.

CHIBIO_MOCK_HW is an *import shim*: it swaps in a no-op GPIO and skips both
setup_watchdog() and initialiseAll(), so `import app` succeeds on a dev laptop for
the test_*.py suite. Because initialise(M) never runs, a lot of sysData keeps its
raw chibio_state template values -- the FP *Record fields stay the int 0 instead of
[], the FP LED/band/Gain fields stay 0 so the GUI's Excite/Baseband/Emit/Gain
dropdowns render empty, and Version['LED'] stays 1 (so a V2 board shows the V1
excitation panel). Fine for imports; actively misleading for UI work.

CHIBIO_SIM fakes the *bus*, not the application. smbus2.SMBus is replaced with a
fake that answers as the multiplexer, the two MCP9808 thermometers, the IR
thermometer, the DAC and the two PWM chips; the AS7341 is too intricate to emulate
register-by-register, so it is substituted one level up at chibio_optics.get_light.
Everything above that is the real product code: initialiseAll(), initialise(M),
scan_devices_sync(), the LED V1/V2 auto-detection (and therefore the FP3 LEDE->LEDH
remap), turnEverythingOff(), setPWM, measure_od's log10/LASERa/LASERb calibration
and dark correction, measure_fp's emit/base ratio and near-saturation guard,
measure_temp, the Thermostat PI loop, RegulateOD, and csvData. So the numbers the
GUI shows are produced the way real numbers are produced.

Behind the fake optics sits a small culture model: logistic growth per reactor,
diluted by whatever Pump1 is actually doing, and a first-order heater/ambient
thermal model driven by the real Heat output. Turbidostat control therefore closes
the loop in simulation -- RegulateOD pumps, the sim culture dilutes, OD comes back
down.

Environment:
    CHIBIO_SIM=1                 enable (implies mock GPIO; no watchdog, no I2C)
    CHIBIO_SIM_LED_VERSION=1|2   LED board version to present (default 2)
    CHIBIO_SIM_REACTORS=M0,..    which reactors answer the presence scan
                                 (default M0-M4, this rig's five physical reactors)
    CHIBIO_SIM_HOURS=12          hours of synthetic history to pre-load (0 = none)
    CHIBIO_SIM_SEED=1            RNG seed; the model is otherwise deterministic

Every simulated reactor's DeviceID is prefixed "SIM-" and its terminal opens with a
SIMULATION MODE line, so a screenshot of the GUI can never be mistaken for a run
against real hardware.
"""

import logging
import math
import os
import random
import time
from datetime import datetime, timedelta

logger = logging.getLogger('chibio')

# Only stdlib at module scope: chibio_hardware imports MOCK_HW from here, so any
# top-level import of ours would be a cycle. Everything else is imported inside
# install() / the sim functions, which is also this codebase's house style for
# cross-module calls (see "Circular imports are intentional" in CLAUDE.md).

SIM = bool(os.environ.get('CHIBIO_SIM'))

# CHIBIO_SIM implies the mock GPIO: there is no point pulsing a real watchdog pin at
# a rig that isn't there, and it must never touch a real bus. chibio_hardware and
# app both gate on this single flag.
MOCK_HW = bool(os.environ.get('CHIBIO_MOCK_HW')) or SIM


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        logger.warning('%s is not an integer, using %s', name, default)
        return default


LED_VERSION = 2 if _env_int('CHIBIO_SIM_LED_VERSION', 2) != 1 else 1
HISTORY_HOURS = max(0.0, float(_env_int('CHIBIO_SIM_HOURS', 12)))
SEED = _env_int('CHIBIO_SIM_SEED', 1)

_DEFAULT_REACTORS = 'M0,M1,M2,M3,M4'  # this rig has five physical reactors
PRESENT = [m.strip() for m in os.environ.get('CHIBIO_SIM_REACTORS', _DEFAULT_REACTORS).split(',') if m.strip()]

# The UI keeps at most 200 points before downsample() kicks in (chibio_experiment),
# so synthetic history is generated at that resolution rather than 1/min.
_HISTORY_POINTS = 200

_AMBIENT_C = 22.0          # room temperature the sim reactors sit in
_HEAT_GAIN = 240.0         # degC/hour at full heater duty
_HEAT_LOSS = 8.0           # 1/hour Newtonian loss to ambient (tau ~ 7.5 min)
_MAX_STEP_HOURS = 2.0      # clamp dt so a long-idle server can't jump the model

# CLEAR-base model for the fluorescence read: a constant excitation-leak floor plus
# 90deg scatter proportional to cell density, before LED power and AS7341 gain.
_FP_BASE_LEAK = 2500.0
_FP_BASE_SCATTER = 9000.0
# Gain the bounded autorange typically settles on (x32), used to put the synthetic
# history's base on the same scale as a live read rather than an arbitrary one.
_FP_TYPICAL_GAIN_SCALE = 32.0 * 0.1  # gain x32 at the default 0.1 LED power

# Per-reactor model state. Deliberately NOT in sysData: that dict is jsonify'd to the
# UI and must stay JSON-serializable product state, not simulator internals.
_sim = {}


# ---------------------------------------------------------------------------
# Culture / thermal model
# ---------------------------------------------------------------------------

def _state(M):
    st = _sim.get(M)
    if st is None:
        rng = random.Random('%s:%d' % (M, SEED))
        st = {
            'rng': rng,
            'od': rng.uniform(0.02, 0.05),      # inoculum
            'mu': rng.uniform(0.45, 0.75),      # 1/hour
            'K': rng.uniform(1.4, 2.2),         # carrying capacity in OD
            'temp': _AMBIENT_C + rng.uniform(-0.4, 0.4),
            'fp': {                             # per-FP expression, OD^-1
                'FP1': rng.uniform(0.04, 0.12),
                'FP2': rng.uniform(0.03, 0.10),
                'FP3': rng.uniform(0.02, 0.08),
            },
            'last': time.time(),
        }
        _sim[M] = st
    return st


def _advance(M, now=None):
    """Step the culture and thermal model to wall-clock `now`."""
    from chibio_state import sysData

    st = _state(M)
    now = time.time() if now is None else now
    dt = min(max(now - st['last'], 0.0) / 3600.0, _MAX_STEP_HOURS)
    st['last'] = now
    if dt <= 0.0:
        return st

    # Logistic growth minus dilution from whatever Pump1 is actually set to. Pump1 is
    # the input pump; RegulateOD drives it, so the turbidostat loop closes here.
    od = st['od']
    growth = st['mu'] * od * (1.0 - od / st['K'])
    pump = sysData[M]['Pump1']
    dilution = 1.5 * abs(float(pump['target'])) * float(pump['ON']) * od
    od = od + (growth - dilution) * dt
    st['od'] = min(max(od, 1e-4), st['K'] * 1.2)

    # First-order heater: the real Heat output (0-1 duty) against Newtonian loss.
    heat = float(sysData[M]['Heat']['target']) * float(sysData[M]['Heat']['ON'])
    temp = st['temp']
    temp = temp + (_HEAT_GAIN * heat - _HEAT_LOSS * (temp - _AMBIENT_C)) * dt
    st['temp'] = min(max(temp, 0.0), 99.0)
    return st


def _od_now(M):
    return _advance(M)['od']


# ---------------------------------------------------------------------------
# Fake optics (AS7341 substitute)
# ---------------------------------------------------------------------------

def _transmission_counts(M, od):
    """Invert measure_od's calibration so the OD it recovers is the OD we modelled.

    measure_od computes  OD = r*b + r^2*a  with  r = log10(blank / transmission),
    so solving the quadratic for r and going back through the log gives the raw
    CLEAR count that produces this OD exactly. Gain is deliberately NOT applied:
    the OD gain is locked to the calibration constants (see the autorange rule in
    CLAUDE.md), so scaling here would silently break the round-trip.
    """
    from chibio_state import sysData

    a = float(sysData[M]['OD0']['LASERa'])
    b = float(sysData[M]['OD0']['LASERb'])
    blank = float(sysData[M]['OD0']['target']) or 65000.0
    if a > 1e-9:
        r = (-b + math.sqrt(max(b * b + 4.0 * a * od, 0.0))) / (2.0 * a)
    elif b:
        r = od / b
    else:
        r = 0.0
    return blank / (10.0 ** max(r, 0.0))


def _active_source(M):
    """Which light output is currently on, as set_output_on_sync left it."""
    from chibio_state import sysData

    for item in ['LASER650', 'LEDA', 'LEDB', 'LEDC', 'LEDD', 'LEDE',
                 'LEDF', 'LEDG', 'LEDH', 'LEDI', 'LEDV', 'UV']:
        if sysData[M].get(item, {}).get('ON', 0) == 1:
            return item, float(sysData[M][item]['target'])
    return None, 0.0


def _fp_for_led(M, led):
    """The FP slot excited by this LED, so emission bands carry its signal."""
    from chibio_state import sysData

    for FP in ['FP1', 'FP2', 'FP3']:
        if sysData[M][FP].get('LED') == led:
            return FP
    return None


def _counts(M, wavelength, source, power, gain_scale, od, rng):
    """Photon counts for one AS7341 channel under the current illumination."""
    if wavelength == 'OFF':
        return 0.0
    if wavelength == 'DARK':
        return 1.0 + rng.uniform(0.0, 1.0)

    # OD path: the calibrated transmission, ungained (see _transmission_counts).
    if source in ('LASER650', 'LEDF', 'LEDA') and wavelength == 'CLEAR':
        return _transmission_counts(M, od) * rng.uniform(0.998, 1.002)

    if source is None:
        return rng.uniform(0.0, 3.0) * gain_scale

    # Fluorescence path. The CLEAR "base" is dominated by excitation leak plus 90deg
    # scatter, which grows with cell density -- this is what drives the base toward the
    # 65535 ceiling and trips measure_fp's near-saturation guard, so the guard is
    # exercisable in simulation. The coefficients are set so that with the default LED
    # power and autorange's bounded 4 retries, the base stays under the 60000 guard
    # through most of a growth curve and only crosses it at high density, matching the
    # proportion measured on a real dense culture (see _FP_BASE_NEAR_SATURATION).
    base = (_FP_BASE_LEAK + _FP_BASE_SCATTER * min(od, 1.6)) * max(power, 0.05) * gain_scale
    if wavelength == 'CLEAR':
        return base * rng.uniform(0.99, 1.01)

    # Emission bands: a few percent of filter bleed-through, plus FP signal
    # proportional to biomass when this band belongs to the FP this LED excites.
    from chibio_state import sysData

    signal = 0.0
    FP = _fp_for_led(M, source)
    if FP is not None:
        level = _state(M)['fp'][FP]
        if wavelength == sysData[M][FP].get('Emit1Band'):
            signal = level * od
        elif wavelength == sysData[M][FP].get('Emit2Band'):
            signal = level * od * 0.45
    return base * (0.02 + signal) * rng.uniform(0.97, 1.03)


def sim_get_light(M, wavelengths, Gain, ISteps, autorange=False):
    """Stand-in for chibio_optics.get_light with the same contract.

    Fills AS7341 channels/current exactly as the real read does (including the
    'valid' and 'gain' keys measure_od and measure_fp go on to read), mirrors the
    real auto-range stepping, and returns the same six-element list.
    """
    from chibio_optics import (NEAR_SATURATION_FRACTION, _AUTORANGE_MAX_TRIES,
                               _AUTORANGE_WEAK, adc_full_scale)
    from chibio_state import sysData

    M = str(M)
    st = _advance(M)
    rng = st['rng']
    od = st['od']

    channels = ['nm410', 'nm440', 'nm470', 'nm510', 'nm550', 'nm583', 'nm620',
                'nm670', 'CLEAR', 'NIR', 'DARK', 'ExtGPIO', 'ExtINT', 'FLICKER']
    for channel in channels:
        sysData[M]['AS7341']['channels'][channel] = 0
    for index, wavelength in enumerate(wavelengths):
        if wavelength != "OFF":
            sysData[M]['AS7341']['channels'][wavelength] = index + 1

    source, power = _active_source(M)
    integration = max(float(ISteps), 1.0) / 255.0

    def read(gain):
        # AS7341 gain codes 0..10 are x0.5 .. x512.
        scale = 0.5 * (2 ** max(min(int(gain), 10), 0)) * integration
        return [_counts(M, w, source, power, scale, od, rng) for w in wavelengths[:6]]

    raw = read(Gain)
    full_scale = adc_full_scale(ISteps)
    hot = full_scale * NEAR_SATURATION_FRACTION  # mirror the real headroom-based step-down
    if autorange:
        tries = 0
        while tries < _AUTORANGE_MAX_TRIES:
            if any(v >= hot for v in raw) and Gain > 0:
                Gain = Gain - 1
            elif raw and max(raw) < _AUTORANGE_WEAK and Gain < 10:
                Gain = Gain + 1
            else:
                break
            raw = read(Gain)
            tries = tries + 1

    DACS = ['ADC0', 'ADC1', 'ADC2', 'ADC3', 'ADC4', 'ADC5']
    for i in range(6):
        value = raw[i] if i < len(raw) else 0.0
        # Clip at the read's real full scale, not always 65535 -- a short integration cannot
        # reach 65535, which is the whole point of adc_full_scale.
        sysData[M]['AS7341']['current'][DACS[i]] = int(min(max(value, 0.0), float(full_scale)))
    sysData[M]['AS7341']['current']['valid'] = 1
    sysData[M]['AS7341']['current']['gain'] = Gain
    sysData[M]['AS7341']['current']['fullScale'] = full_scale
    # Mirrors STATUS2's ASAT bits, which on real hardware fire as the ADC pins. (The chip does
    # not report the gain it applied -- ASTATUS reads 0x00 on this rig -- so nothing to model.)
    sysData[M]['AS7341']['current']['saturated'] = 1 if any(
        v >= full_scale for v in raw) else 0

    output = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for index, wavelength in enumerate(wavelengths[:6]):
        if wavelength != "OFF":
            output[index] = sysData[M]['AS7341']['current'][DACS[index]]
    return output


def sim_get_spectrum(M, Gain):
    """Stand-in for chibio_optics.get_spectrum (feeds the Full Spectral panel)."""
    from chibio_state import sysData

    M = str(M)
    bands = ['nm410', 'nm440', 'nm470', 'nm510', 'nm550', 'nm583']
    sim_get_light(M, bands, Gain, 255)
    for i, band in enumerate(bands):
        sysData[M]['AS7341']['spectrum'][band] = sysData[M]['AS7341']['current']['ADC%d' % i]
    bands2 = ['nm620', 'nm670', 'CLEAR', 'NIR']
    sim_get_light(M, bands2, Gain, 255)
    for i, band in enumerate(bands2):
        sysData[M]['AS7341']['spectrum'][band] = sysData[M]['AS7341']['current']['ADC%d' % i]


# ---------------------------------------------------------------------------
# Fake I2C bus
# ---------------------------------------------------------------------------

_MUX_ADDR = 0x74
_ADDR_THERM_INT = 0x18
_ADDR_THERM_EXT = 0x1b
_ADDR_THERM_IR = 0x5a


# One state blob per bus number. There is only ever one physical bus 2, but the code
# opens several handles onto it (chibio_hardware._get_bus caches one, and initialise()
# additionally does smbus.SMBus(bus=2) per reactor for the IR thermometer). All of them
# must see the same multiplexer channel, so the state lives here rather than on the
# instance -- otherwise a read through one handle is routed by another handle's channel.
_BUS_STATE = {}


class _FakeBus:
    """Replaces smbus2.SMBus. Every handle on a bus number shares one bus state.

    Answers as the multiplexer plus the non-spectrometer devices on each reactor, and
    raises OSError for reactors that aren't in CHIBIO_SIM_REACTORS -- which is how a
    reactor comes out absent: scan_devices_sync's ThermometerInternal poll fails three
    times and I2CCom sets present=0, exactly as with an empty slot on real hardware.
    """

    def __init__(self, bus=None, *args, **kwargs):
        self.busnum = bus
        self._state = _BUS_STATE.setdefault(bus, {'channel': 0x00, 'registers': {}})

    @property
    def _channel(self):
        return self._state['channel']

    @_channel.setter
    def _channel(self, value):
        self._state['channel'] = value

    @property
    def _registers(self):
        return self._state['registers']

    # -- helpers ---------------------------------------------------------
    def _current_M(self):
        from chibio_state import sysItems

        if not self._channel:
            return None
        for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']:
            if int(sysItems['Multiplexer'][M], 2) == self._channel:
                return M
        return None

    def _require_present(self):
        M = self._current_M()
        if M is None or M not in PRESENT:
            # errno 121 EREMOTEIO is what a real unanswered address raises.
            raise OSError(121, 'Remote I/O error (simulated empty reactor slot)')
        return M

    @staticmethod
    def _swap(word):
        # readU16(..., little_endian=False) byte-swaps, so pre-swap here to make the
        # value the application finally sees come out right. The swap is its own
        # inverse, so one helper covers both directions.
        return ((word << 8) & 0xFF00) + (word >> 8)

    def _thermometer_word(self, celsius):
        # MCP9808 ambient register as measure_temp parses it: bin(word)[6:] keeps the
        # low 12 bits ONLY when the word is a full 16 bits wide, so bit 15 must be set
        # (on real silicon those top bits are the alert flags). value = 16 * degC.
        return self._swap(0x8000 | (int(round(celsius * 16.0)) & 0x0FFF))

    # -- SMBus surface ---------------------------------------------------
    def write_byte_data(self, addr, register, value):
        if addr == _MUX_ADDR:
            self._channel = value & 0xFF
            return
        self._require_present()
        self._registers[(addr, register)] = value & 0xFF

    def write_word_data(self, addr, register, value):
        self._require_present()
        self._registers[(addr, register)] = value & 0xFFFF

    def read_byte(self, addr):
        if addr == _MUX_ADDR:
            return self._channel
        self._require_present()
        return 0

    def read_byte_data(self, addr, register):
        self._require_present()
        return self._registers.get((addr, register), 0)

    def read_word_data(self, addr, register):
        M = self._require_present()
        st = _advance(M)

        if addr == _ADDR_THERM_INT:
            return self._thermometer_word(st['temp'])
        if addr == _ADDR_THERM_EXT:
            # The external probe sits in air, between ambient and the culture.
            return self._thermometer_word(_AMBIENT_C + (st['temp'] - _AMBIENT_C) * 0.35)
        if addr == _ADDR_THERM_IR:
            if register == 0x07:  # object temperature, 0.02 K per count
                return int((st['temp'] + 273.15) / 0.02)
            if register in (0x3C, 0x3D, 0x3E, 0x3F):
                # Serial-number words; GetID concatenates them into DeviceID.
                return (SEED * 7919 + int(M[1:]) * 1013 + register) & 0xFFFF
            return 0
        return self._registers.get((addr, register), 0)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Synthetic history
# ---------------------------------------------------------------------------

def _synthesise_history(M, hours):
    """Back-fill the record arrays so the charts open with a plausible run.

    Every record list must come out the same length as time.record -- uPlot is fed
    these as parallel series. Values are produced by the same logistic model the live
    simulation uses, and the model's biomass is left at the end of the curve so live
    measurements continue from where the history stops.
    """
    from chibio_state import sysData

    st = _state(M)
    rng = st['rng']
    n = _HISTORY_POINTS
    span = hours * 3600.0
    now = time.time()

    mu, K = st['mu'], st['K']
    od0 = st['od']
    thermostat_target = float(sysData[M]['Thermostat']['default'])

    times, ods, corrected, spreads, temps_int, temps_ext, temps_ir, growth = ([] for _ in range(8))
    fp_base = {'FP1': [], 'FP2': [], 'FP3': []}
    fp_e1 = {'FP1': [], 'FP2': [], 'FP3': []}
    fp_e2 = {'FP1': [], 'FP2': [], 'FP3': []}

    for i in range(n):
        t = span * i / float(n - 1) if n > 1 else 0.0
        h = t / 3600.0
        # Closed-form logistic, so history matches the differential model above.
        od = K / (1.0 + ((K - od0) / od0) * math.exp(-mu * h))
        od = max(od * rng.uniform(0.99, 1.01), 1e-4)
        # Heater warms to setpoint over the first ~20 min, then ripples under PI.
        temp = _AMBIENT_C + (thermostat_target - _AMBIENT_C) * (1.0 - math.exp(-h * 3.0))
        temp += rng.uniform(-0.15, 0.15)

        times.append(t)
        ods.append(od)
        corrected.append(od * rng.uniform(0.995, 1.005))
        spreads.append(abs(rng.gauss(0.0, 0.004)))
        temps_int.append(temp)
        temps_ext.append(_AMBIENT_C + (temp - _AMBIENT_C) * 0.35 + rng.uniform(-0.1, 0.1))
        temps_ir.append(temp + rng.uniform(-0.3, 0.3))
        growth.append(max(mu * (1.0 - od / K) + rng.gauss(0.0, 0.02), 0.0))
        for FP in ['FP1', 'FP2', 'FP3']:
            # Same base model as a live read, at the gain autorange usually settles on,
            # and clamped: the CLEAR base is a 16-bit ADC count, so it cannot exceed
            # 65535 however dense the culture gets.
            base = min((_FP_BASE_LEAK + _FP_BASE_SCATTER * min(od, 1.6)) * _FP_TYPICAL_GAIN_SCALE, 65535.0)
            level = st['fp'][FP]
            fp_base[FP].append(base)
            fp_e1[FP].append(0.02 + level * od * rng.uniform(0.97, 1.03))
            fp_e2[FP].append(0.02 + level * od * 0.45 * rng.uniform(0.97, 1.03))

    zeros = [0.0] * n
    sysData[M]['time']['record'] = times
    sysData[M]['OD']['record'] = ods
    sysData[M]['OD']['targetrecord'] = list(zeros)
    sysData[M]['OD']['spreadRecord'] = spreads
    sysData[M]['OD']['correctedRecord'] = corrected
    sysData[M]['Thermostat']['record'] = [thermostat_target] * n
    sysData[M]['Light']['record'] = list(zeros)
    sysData[M]['ThermometerInternal']['record'] = temps_int
    sysData[M]['ThermometerExternal']['record'] = temps_ext
    sysData[M]['ThermometerIR']['record'] = temps_ir
    for pump in ['Pump1', 'Pump2', 'Pump3', 'Pump4']:
        sysData[M][pump]['record'] = list(zeros)
    sysData[M]['GrowthRate']['record'] = growth
    for FP in ['FP1', 'FP2', 'FP3']:
        sysData[M][FP]['BaseRecord'] = fp_base[FP]
        sysData[M][FP]['Emit1Record'] = fp_e1[FP]
        sysData[M][FP]['Emit2Record'] = fp_e2[FP]

    # Leave the model where the history ended so live reads continue the curve, and
    # present the run as one that started `hours` ago but is not currently running.
    st['od'] = ods[-1]
    st['temp'] = temps_int[-1]
    st['last'] = now
    sysData[M]['Experiment']['cycles'] = n
    # runExperiment does `datetime.now() - startTimeRaw`, so this must be a datetime,
    # not a POSIX timestamp -- a float here crashes the experiment thread on its first
    # cycle (TypeError: datetime - float). Matches what the /Experiment route stores.
    started = datetime.now() - timedelta(seconds=span)
    sysData[M]['Experiment']['startTimeRaw'] = started
    sysData[M]['Experiment']['startTime'] = started.strftime("%Y-%m-%d %H:%M:%S")
    sysData[M]['OD']['current'] = ods[-1]
    sysData[M]['OD']['corrected'] = corrected[-1]
    # Keep the raw/dark transmission consistent with the OD the history ended on,
    # otherwise the UI shows a final OD next to an unmeasured blank-valued raw count.
    sysData[M]['OD0']['raw'] = _transmission_counts(M, ods[-1])
    sysData[M]['OD0']['dark'] = 1.0
    sysData[M]['OD0']['rawCorrected'] = sysData[M]['OD0']['raw'] - 1.0
    sysData[M]['GrowthRate']['current'] = growth[-1]
    sysData[M]['ThermometerInternal']['current'] = temps_int[-1]
    sysData[M]['ThermometerExternal']['current'] = temps_ext[-1]
    sysData[M]['ThermometerIR']['current'] = temps_ir[-1]
    for FP in ['FP1', 'FP2', 'FP3']:
        sysData[M][FP]['Base'] = fp_base[FP][-1]
        sysData[M][FP]['Emit1'] = fp_e1[FP][-1]
        sysData[M][FP]['Emit2'] = fp_e2[FP][-1]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _patch_optics():
    """Swap get_light/get_spectrum for the simulated versions.

    get_transmission calls get_light through module globals, so patching the module
    attribute covers measure_od/measure_fp (which import get_transmission, not
    get_light) and chibio_fluorescence (which imports get_light lazily). app.py binds
    get_light/get_spectrum at import time, so its namespace needs patching directly
    -- that binding is what the LED V1/V2 auto-detection calls.
    """
    import sys

    import chibio_optics

    chibio_optics.get_light = sim_get_light
    chibio_optics.get_spectrum = sim_get_spectrum
    for name in ('app', '__main__'):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, 'get_light'):
            module.get_light = sim_get_light
            module.get_spectrum = sim_get_spectrum


def _patch_bus():
    import smbus2

    import chibio_hardware

    smbus2.SMBus = _FakeBus
    chibio_hardware._i2c_buses.clear()  # drop any handle opened before the swap


def install():
    """Patch the hardware layer, then run the real initialiseAll() on top of it."""
    if not SIM:
        return

    _patch_bus()
    _patch_optics()

    import sys

    from chibio_state import sysData

    # install() is called from the bottom of app.py, so the module is already in
    # sys.modules (fully defined, still executing). `import app` would re-execute it
    # as a second module when the server is started as `python app.py`, running
    # initialiseAll twice -- take the live module object instead.
    app = sys.modules.get('app') or sys.modules['__main__']

    logger.info('SIMULATION MODE: reactors=%s LED version=%s history=%sh seed=%s',
                ','.join(PRESENT), LED_VERSION, HISTORY_HOURS, SEED)

    # The V1/V2 detection pulses LEDG/LEDH and watches nm583, so the simulated
    # spectrometer has to answer in a way that yields the requested version. Rather
    # than force Version['LED'] afterwards (which would skip the FP3 LEDE->LEDH
    # remap that hangs off it), make the sim optics respond to the right LED.
    detect_led = 'LEDH' if LED_VERSION == 2 else 'LEDG'
    original_counts = globals()['_counts']

    def _detection_counts(M, wavelength, source, power, gain_scale, od, rng):
        if source in ('LEDG', 'LEDH'):
            return 5000.0 if source == detect_led else 1.0
        return original_counts(M, wavelength, source, power, gain_scale, od, rng)

    globals()['_counts'] = _detection_counts
    try:
        app.initialiseAll()
    finally:
        globals()['_counts'] = original_counts

    for M in PRESENT:
        if sysData[M]['present'] != 1:
            logger.warning('SIMULATION: %s did not come up present', M)
            continue
        # Make the simulation unmistakable in the UI itself, without touching any
        # template: the device ID is rendered in the header and the terminal is on
        # screen. No screenshot of this can be mistaken for real hardware.
        sysData[M]['DeviceID'] = 'SIM-' + str(sysData[M]['DeviceID'])[:12]
        app.addTerminal(M, 'SIMULATION MODE - no hardware attached')
        app.addTerminal(M, 'LED version ' + str(sysData[M]['Version']['LED']) + ' (simulated)')
        if HISTORY_HOURS > 0:
            _synthesise_history(M, HISTORY_HOURS)
            app.addTerminal(M, str(int(HISTORY_HOURS)) + 'h of synthetic history pre-loaded')

    logger.info('SIMULATION MODE ready: %s present, %s absent',
                [M for M in PRESENT if sysData[M]['present'] == 1],
                [M for M in ['M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7']
                 if sysData[M]['present'] != 1])
