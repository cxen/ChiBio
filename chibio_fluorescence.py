"""Fluorescence configuration assist: scan the sample across the available excitation
LEDs, read the emission spectrum, and recommend the best DISCRETE hardware settings
(excitation LED + emission detection bands + gain) for an FP measurement.

The control is coarse -- a fixed set of excitation LEDs and a fixed set of AS7341
detection bands (the "filters") -- so the job is exactly to pick the best available
combination, which is then applied to an FP slot via the normal SetFPMeasurement path.
"""
import copy
import time
import logging

from chibio_hardware import measurement_sequence
from chibio_state import sysData, sysItems

logger = logging.getLogger('chibio')

# Excitation LED -> approximate peak wavelength (nm). The available LEDs differ by control-board
# LED version (see the FPExcite dropdowns in HTMLScripts.js); only the reasonably monochromatic
# ones are used as excitation sources (white LEDs left out). Driving an LED absent on this board
# would be a silent no-op, so pick the set that actually exists.
_EXCITATION_V1 = [('LEDA', 395), ('LEDB', 457), ('LEDC', 500), ('LEDD', 523), ('LEDE', 595), ('LEDF', 623)]
_EXCITATION_V2 = [('LEDB', 457), ('LEDC', 500), ('LEDD', 523), ('LEDI', 550), ('LEDH', 600), ('LEDF', 623)]


def excitation_leds(M):
    return _EXCITATION_V2 if sysData[M].get('Version', {}).get('LED') == 2 else _EXCITATION_V1
# AS7341 emission channel -> center wavelength (nm). These are the discrete detection bands.
EMISSION_BANDS = [('nm410', 410), ('nm440', 440), ('nm470', 470), ('nm510', 510),
                  ('nm550', 550), ('nm583', 583), ('nm620', 620), ('nm670', 670)]
# Emission must be at least this far to the red of the excitation to count as fluorescence
# (Stokes shift) rather than excitation scatter bleeding into the detector.
STOKES_MIN_SHIFT = 20
_QUICK_POWER = 0.5
_FULL_POWERS = [0.25, 0.5, 1.0]
_SCAN_READ_RETRIES = 2  # extra re-reads of a spectrum before accepting a valid=0 (transient) dropout


def _gain_multiplier(gain_index):
    # AS7341 gain index 0..10 maps to 0.5x, 1x, 2x, ... 512x. Normalising counts by this makes
    # readings taken at different (auto-ranged) gains directly comparable.
    return 0.5 * (2 ** int(gain_index))


def _emission_spectrum(M):
    # Read all 8 narrow emission bands. Auto-range on the first (6-band) read, then reuse that
    # gain for the second (2-band) read so all 8 bands share one gain and stay comparable.
    # A failed AS7341 read keeps the LAST-KNOWN counts (see sensor-failure-semantics), so an
    # unflagged dropout would bake a stale/zero value into the EEM at the wrong gain and skew the
    # gain-normalisation. Carry the per-read validity through (_valid = both reads valid) so the
    # caller can retry or drop the cell instead of trusting it.
    from chibio_optics import get_light
    b1 = ['nm410', 'nm440', 'nm470', 'nm510', 'nm550', 'nm583']
    b2 = ['nm620', 'nm670']
    o1 = get_light(M, b1, 6, 255, autorange=True)
    v1 = sysData[M]['AS7341']['current'].get('valid', 1)
    g = int(sysData[M]['AS7341']['current'].get('gain', 6))
    o2 = get_light(M, b2, g, 255)
    v2 = sysData[M]['AS7341']['current'].get('valid', 1)
    spec = {'_gain': g, '_valid': 1 if (v1 and v2) else 0}
    for i, b in enumerate(b1):
        spec[b] = o1[i]
    for i, b in enumerate(b2):
        spec[b] = o2[i]
    return spec


# A peak must exceed the row's noise floor by this factor to count as real fluorescence
# (rather than uniform scatter/noise across the emission bands).
_PEAK_OVER_FLOOR = 1.5

# --- matched non-fluorescent reference subtraction -------------------------------------------
# Measured on the rig 2026-08-13, four reactors holding non-fluorescent material (three WT
# cultures + one sterile-medium blank), quick scans at LED power 0.5:
#
#   * every reactor -- INCLUDING the sterile blank -- was handed the same confident
#     recommendation, LEDI(550) -> nm583/nm620, and its reported "signal" tracked turbidity
#     (sterile 37.7, WT 269.6/275.9, denser WT 516.2). The recommender was reading biomass.
#   * subtracting a matched non-fluorescent EEM after fitting ONE scale factor removes ~92% of
#     that background: |residual|/signal came out at a median 6-8% between reactors of similar
#     density and 14-16% across a 1.8x density difference.
#   * a sterile blank is NOT a substitute for a matched culture: sterile-vs-culture left a 20-22%
#     median residual, because medium scatters differently from cells.
#   * scan-to-scan repeatability on unchanged samples was ~0.1-3%, so the residual floor is set
#     by how well the reference matches the sample, not by read noise.
#
# ponytail: 0.25 is the WT-vs-WT floor above (max ~16% median, p90 ~40% at mismatched density)
# plus margin. Retune against a reactor holding a KNOWN fluorophore -- no such measurement exists
# on this rig yet, so this threshold is calibrated only against true negatives.
_REFERENCE_RESIDUAL_MIN = 0.25
# A fitted scale far from 1 means the reference was taken at a very different density, which
# inflates the residual floor (measured: 6-8% matched vs 14-16% at 1.8x).
_REFERENCE_SCALE_WARN = (0.5, 2.0)


def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _reference_scale(eem, reference):
    # One scale factor relating the reference EEM to this one. Median of the per-cell ratios:
    # the scale must be estimated from the BACKGROUND, and a real fluorophore perturbs only a
    # cell or two, which a median ignores and a sum-based fit does not. (Measured: median-ratio,
    # sum/sum and scatter-peak-only estimators agreed to within ~1% of residual on real data;
    # the median is the one that stays honest when a genuine FP is present.)
    ratios = []
    for led, row in eem.items():
        ref = reference.get(led)
        if row is None or ref is None or row.get('_valid', 1) == 0 or ref.get('_valid', 1) == 0:
            continue
        for b, _ in EMISSION_BANDS:
            r = float(ref.get(b, 0.0))
            if r > 1.0:  # ignore cells sitting at the read floor
                ratios.append(float(row.get(b, 0.0)) / r)
    return _median(ratios) if ratios else None


def subtract_reference(eem, reference):
    # Return (residual EEM, scale, background EEM). The residual is what is left of the sample
    # once a matched non-fluorescent sample -- scaled to the same biomass -- is taken away.
    scale = _reference_scale(eem, reference)
    if not scale or scale <= 0:
        return None, None, None
    resid, background = {}, {}
    for led, row in eem.items():
        ref = reference.get(led)
        if row is None or ref is None:
            continue
        rrow = {'_wl': row['_wl'], '_gain': row.get('_gain'), '_power': row.get('_power'),
                '_valid': 1 if (row.get('_valid', 1) and ref.get('_valid', 1)) else 0}
        brow = dict(rrow)
        for b, _ in EMISSION_BANDS:
            bg = scale * float(ref.get(b, 0.0))
            brow[b] = round(bg, 3)
            rrow[b] = round(float(row.get(b, 0.0)) - bg, 3)
        resid[led] = rrow
        background[led] = brow
    return resid, scale, background


def recommend_fp_settings(eem, reference=None):
    # Pure analysis over the excitation-emission matrix: pick the best DISCRETE
    # (excite LED, Emit1, Emit2, gain) using the Stokes-shift rule. Returns None if nothing
    # cleared the shift OR the best "peak" doesn't stand above the noise floor (a non-fluorescent
    # sample). Base band is CLEAR (broadband reference).
    #
    # `reference` is an EEM of matched NON-fluorescent material (ideally the same strain without
    # the FP, at a similar density, on the same reactor). Given one, the pick is made on the
    # residual after subtracting it -- which is the only way measured on this rig to tell a
    # fluorophore from the excitation leak and scatter that dominate every raw EEM. Without one
    # the old behaviour is preserved but the result is labelled `confidence: 'unreferenced'`,
    # because a sterile tube of medium earns the same confident answer as a culture.
    band_wl = dict(EMISSION_BANDS)
    scale = residual = background = None
    search = eem
    if reference:
        residual, scale, background = subtract_reference(eem, reference)
        if residual:
            search = residual

    best = None  # (signal, led, band)
    for led, row in search.items():
        if row is None or row.get('_valid', 1) == 0:
            continue  # a dead read's stale/zero counts must not be recommended
        led_wl = row['_wl']
        for b, wl in EMISSION_BANDS:
            if wl >= led_wl + STOKES_MIN_SHIFT:
                sig = row.get(b, 0.0)
                if best is None or sig > best[0]:
                    best = (sig, led, b)
    if best is None:
        return None
    sig, led, emit1 = best
    if residual:
        # The residual must clear both the read noise AND a fixed fraction of the background it
        # was subtracted from -- a 5-count residual on a 2000-count background is a scale-fit
        # artefact, not a fluorophore.
        bg = background[led].get(emit1, 0.0)
        if sig <= 0 or sig < _REFERENCE_RESIDUAL_MIN * abs(bg):
            return None
        floor = _median([abs(residual[led].get(b, 0.0)) for b, _ in EMISSION_BANDS])
        if sig < _PEAK_OVER_FLOOR * floor:
            return None
        return _recommendation(residual, led, emit1, sig, band_wl,
                               confidence='referenced', scale=scale,
                               background=round(float(bg), 2))
    floor = _median([eem[led].get(b, 0.0) for b, _ in EMISSION_BANDS])
    if sig <= 0 or sig < _PEAK_OVER_FLOOR * floor:
        return None  # no peak stands out -> nothing to recommend
    return _recommendation(eem, led, emit1, sig, band_wl, confidence='unreferenced')


def _recommendation(source, led, emit1, sig, band_wl, confidence,
                    scale=None, background=None):
    row = source[led]
    # Emit2 = the next-strongest Stokes-shifted band for the same LED (a second readout channel).
    others = sorted(((row.get(b, 0.0), b) for b, wl in EMISSION_BANDS
                     if wl >= row['_wl'] + STOKES_MIN_SHIFT and b != emit1), reverse=True)
    emit2 = others[0][1] if others else emit1
    rec = {
        'excite': led, 'excite_nm': row['_wl'],
        'base': 'CLEAR',
        'emit1': emit1, 'emit1_nm': band_wl[emit1],
        'emit2': emit2, 'emit2_nm': band_wl[emit2],
        'gain': 'x%d' % int(row['_gain']),
        'signal': round(float(sig), 2),
        'confidence': confidence,
    }
    if confidence == 'referenced':
        rec['reference_scale'] = round(float(scale), 3)
        rec['background'] = background
        rec['signal_over_background'] = (round(float(sig) / abs(background), 3)
                                         if background else None)
        lo, hi = _REFERENCE_SCALE_WARN
        if not (lo <= scale <= hi):
            rec['warning'] = ('reference taken at a very different density (fitted scale %.2f); '
                              'the residual floor rises with mismatch -- re-reference near this '
                              'density before trusting the number' % scale)
    else:
        rec['warning'] = ('no matched non-fluorescent reference: this pick cannot be separated '
                          'from excitation leak and scatter, both of which scale with biomass. '
                          'On this rig a STERILE tube of medium earns the same recommendation as '
                          'a culture. Scan a matched no-FP reactor and set it as the reference.')
    return rec


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
    sysData[M]['FluorescenceScan'] = {'matrix': {}, 'recommendation': None, 'mode': mode,
                                      'status': 'running', 'bands': [b for b, _ in EMISSION_BANDS]}

    eem = {}
    for led, wl in excitation_leds(M):
        best_row = None
        for p in powers:
            # Hold the reactor's measurement mutex across this LED's whole drive->read->off.
            # Without it the scan and the reactor's own experiment cycle interleave on the
            # same hardware -- the scan switches a light off between the cycle's switch-on
            # and its read (an unflagged raw=0 row), and on 2026-08-11 that collision also
            # killed M3's experiment thread outright. Per-LED rather than around the whole
            # scan so a waiting cycle only queues for one read, not the entire sweep.
            with measurement_sequence(M):
                set_output_target_sync(M, led, p)
                set_output_on_sync(M, led, 1)
                try:
                    # Dropouts are transient, so re-read a couple of times before accepting an
                    # invalid spectrum; only a genuinely dead read reaches the EEM, carrying _valid=0.
                    for _attempt in range(_SCAN_READ_RETRIES + 1):
                        time.sleep(0.1)
                        spec = _emission_spectrum(M)
                        if spec['_valid']:
                            break
                finally:
                    set_output_on_sync(M, led, 0) #never leave an excitation LED on
            mult = _gain_multiplier(spec['_gain'])
            row = {'_gain': spec['_gain'], '_wl': wl, '_power': p, '_valid': spec['_valid']}
            total = 0.0
            for b, _ in EMISSION_BANDS:
                v = float(spec[b]) / mult
                row[b] = round(v, 3)
                total += v
            # Prefer a valid row over any invalid one, then the strongest total among same-validity.
            if best_row is None or (row['_valid'], total) > (best_row['_valid'], best_row['_total']):
                row['_total'] = total
                best_row = row
        best_row.pop('_total', None)
        eem[led] = best_row
        addTerminal(M, 'Scanned ' + led + ' (' + str(wl) + 'nm)')

    ref = reference_matrix(M)
    result = {
        'matrix': eem,
        'recommendation': recommend_fp_settings(eem, ref),
        'status': 'done',
        'referenced': 1 if ref else 0,
    }
    if ref:
        residual, scale, _bg = subtract_reference(eem, ref)
        result['residual'] = residual
        result['reference_scale'] = round(float(scale), 3) if scale else None
        result['reference_from'] = sysData[M]['FluorescenceReference'].get('from')
    sysData[M]['FluorescenceScan'].update(result)
    addTerminal(M, 'Fluorescence scan complete'
                + (' (vs reference ' + str(result.get('reference_from')) + ')' if ref else ''))


def reference_matrix(M):
    # The reference EEM lives in sysDevices, not sysData: sysData is jsonified to the browser on
    # every 1 s poll, and a 6x8 matrix of floats per reactor would ride along on each one for a
    # value the UI never reads. sysData keeps only the small 'from'/'time' pair it does display.
    from chibio_state import sysDevices
    return sysDevices[str(M)].get('fluorReferenceMatrix') or None


def set_fluorescence_reference(M, source):
    # Adopt a scan as this reactor's matched non-fluorescent reference. `source` is the reactor
    # whose most recent completed scan to take ('self' for this one, 'clear' to drop it).
    # Cross-reactor is allowed and is often what you want -- the control lives in its own vial --
    # but it costs accuracy: measured on this rig, WT-vs-WT subtraction left a 6-8% residual at
    # matched density against 20-22% for sterile-medium-vs-culture.
    from app import addTerminal
    from chibio_control_helpers import logEvent
    from chibio_state import sysDevices
    M = str(M)
    if M == "0":
        M = sysItems['UIDevice']
    source = str(source)
    if source == 'clear':
        sysData[M]['FluorescenceReference'] = {'from': '', 'time': ''}
        sysDevices[M]['fluorReferenceMatrix'] = None
        addTerminal(M, 'Fluorescence reference cleared')
        logEvent(M, 'fluorescence_reference', {'from': None})
        return True
    src = M if source == 'self' else source
    if src not in sysData:
        addTerminal(M, 'Fluorescence reference: no such device ' + src)
        return False
    scan = sysData[src].get('FluorescenceScan') or {}
    if scan.get('status') != 'done' or not scan.get('matrix'):
        addTerminal(M, 'Fluorescence reference: ' + src + ' has no completed scan to use')
        return False
    sysDevices[M]['fluorReferenceMatrix'] = copy.deepcopy(scan['matrix'])
    sysData[M]['FluorescenceReference'] = {
        'from': src,
        'time': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    addTerminal(M, 'Fluorescence reference set from ' + src)
    logEvent(M, 'fluorescence_reference', {'from': src, 'leds': sorted(scan['matrix'].keys())})
    return True
