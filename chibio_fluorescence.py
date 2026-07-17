"""Fluorescence configuration assist: scan the sample across the available excitation
LEDs, read the emission spectrum, and recommend the best DISCRETE hardware settings
(excitation LED + emission detection bands + gain) for an FP measurement.

The control is coarse -- a fixed set of excitation LEDs and a fixed set of AS7341
detection bands (the "filters") -- so the job is exactly to pick the best available
combination, which is then applied to an FP slot via the normal SetFPMeasurement path.
"""
import time
import logging

from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')

# Excitation LED -> approximate peak wavelength (nm). Only the reasonably monochromatic
# LEDs make sense as excitation sources; the white LEDs (LEDG/LEDV) are left out of the scan.
EXCITATION_LEDS = [('LEDA', 395), ('LEDB', 457), ('LEDC', 500), ('LEDD', 523),
                   ('LEDI', 550), ('LEDE', 595), ('LEDH', 600), ('LEDF', 623)]
# AS7341 emission channel -> center wavelength (nm). These are the discrete detection bands.
EMISSION_BANDS = [('nm410', 410), ('nm440', 440), ('nm470', 470), ('nm510', 510),
                  ('nm550', 550), ('nm583', 583), ('nm620', 620), ('nm670', 670)]
# Emission must be at least this far to the red of the excitation to count as fluorescence
# (Stokes shift) rather than excitation scatter bleeding into the detector.
STOKES_MIN_SHIFT = 20
_QUICK_POWER = 0.5
_FULL_POWERS = [0.25, 0.5, 1.0]


def _gain_multiplier(gain_index):
    # AS7341 gain index 0..10 maps to 0.5x, 1x, 2x, ... 512x. Normalising counts by this makes
    # readings taken at different (auto-ranged) gains directly comparable.
    return 0.5 * (2 ** int(gain_index))


def _emission_spectrum(M):
    # Read all 8 narrow emission bands. Auto-range on the first (6-band) read, then reuse that
    # gain for the second (2-band) read so all 8 bands share one gain and stay comparable.
    from chibio_optics import get_light
    b1 = ['nm410', 'nm440', 'nm470', 'nm510', 'nm550', 'nm583']
    b2 = ['nm620', 'nm670']
    o1 = get_light(M, b1, 6, 255, autorange=True)
    g = int(sysData[M]['AS7341']['current'].get('gain', 6))
    o2 = get_light(M, b2, g, 255)
    spec = {'_gain': g}
    for i, b in enumerate(b1):
        spec[b] = o1[i]
    for i, b in enumerate(b2):
        spec[b] = o2[i]
    return spec


# A peak must exceed the row's noise floor by this factor to count as real fluorescence
# (rather than uniform scatter/noise across the emission bands).
_PEAK_OVER_FLOOR = 1.5


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def recommend_fp_settings(eem):
    # Pure analysis over the excitation-emission matrix: pick the best DISCRETE
    # (excite LED, Emit1, Emit2, gain) using the Stokes-shift rule. Returns None if nothing
    # cleared the shift OR the best "peak" doesn't stand above the noise floor (a non-fluorescent
    # sample). Base band is CLEAR (broadband reference).
    band_wl = dict(EMISSION_BANDS)
    best = None  # (signal, led, band)
    for led, row in eem.items():
        led_wl = row['_wl']
        for b, wl in EMISSION_BANDS:
            if wl >= led_wl + STOKES_MIN_SHIFT:
                sig = row.get(b, 0.0)
                if best is None or sig > best[0]:
                    best = (sig, led, b)
    if best is None:
        return None
    sig, led, emit1 = best
    floor = _median([eem[led].get(b, 0.0) for b, _ in EMISSION_BANDS])
    if sig <= 0 or sig < _PEAK_OVER_FLOOR * floor:
        return None  # no peak stands out -> nothing to recommend
    row = eem[led]
    # Emit2 = the next-strongest Stokes-shifted band for the same LED (a second readout channel).
    others = sorted(((row.get(b, 0.0), b) for b, wl in EMISSION_BANDS
                     if wl >= row['_wl'] + STOKES_MIN_SHIFT and b != emit1), reverse=True)
    emit2 = others[0][1] if others else emit1
    return {
        'excite': led, 'excite_nm': row['_wl'],
        'base': 'CLEAR',
        'emit1': emit1, 'emit1_nm': band_wl[emit1],
        'emit2': emit2, 'emit2_nm': band_wl[emit2],
        'gain': 'x%d' % int(row['_gain']),
        'signal': round(float(sig), 2),
    }


def fluorescence_scan(M, mode='quick'):
    # Drive each excitation LED, read the emission spectrum, and build a gain-normalised EEM in
    # sysData plus a recommended FP configuration. mode 'quick' = one power/LED; 'full' = a small
    # power sweep (keeps the strongest response per LED). Reuses the auto-ranging read path.
    from app import set_output_on_sync, set_output_target_sync, addTerminal
    M = str(M)
    if M == "0":
        M = sysItems['UIDevice']
    mode = 'full' if str(mode) == 'full' else 'quick'
    powers = _FULL_POWERS if mode == 'full' else [_QUICK_POWER]
    addTerminal(M, 'Fluorescence scan (' + mode + ') started')

    eem = {}
    for led, wl in EXCITATION_LEDS:
        best_total, best_row = -1.0, None
        for p in powers:
            set_output_target_sync(M, led, p)
            set_output_on_sync(M, led, 1)
            time.sleep(0.1)
            spec = _emission_spectrum(M)
            set_output_on_sync(M, led, 0)
            mult = _gain_multiplier(spec['_gain'])
            row = {'_gain': spec['_gain'], '_wl': wl, '_power': p}
            total = 0.0
            for b, _ in EMISSION_BANDS:
                v = float(spec[b]) / mult
                row[b] = round(v, 3)
                total += v
            if total > best_total:
                best_total, best_row = total, row
        eem[led] = best_row
        addTerminal(M, 'Scanned ' + led + ' (' + str(wl) + 'nm)')

    sysData[M]['FluorescenceScan'] = {
        'matrix': eem,
        'recommendation': recommend_fp_settings(eem),
        'mode': mode,
        'bands': [b for b, _ in EMISSION_BANDS],
    }
    addTerminal(M, 'Fluorescence scan complete')
