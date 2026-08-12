"""Off-device tests for AS7341 saturation detection and headroom-aware auto-ranging.

Run: CHIBIO_MOCK_HW=1 python3 test_saturation.py

Covers the two audit defects of 2026-08-11: full scale is (ATIME+1)x(ASTEP+1) capped at
65535 rather than always 65535, and the chip's own ASAT flag was read and discarded.
"""
import os

os.environ.setdefault('CHIBIO_MOCK_HW', '1')

import chibio_optics
from chibio_optics import NEAR_SATURATION_FRACTION, adc_full_scale, get_light
from chibio_measurements import _fp_valid_flag
from chibio_state import sysData


def test_full_scale_is_integration_dependent():
    # ams DS000504 Eq. 2, with the ASTEP=999 this code now writes explicitly.
    assert adc_full_scale(10) == 11000, adc_full_scale(10)   # the LED-detection read
    assert adc_full_scale(255) == 65535, adc_full_scale(255)  # OD/FP reads: capped
    assert adc_full_scale(0) == 1000, adc_full_scale(0)
    assert adc_full_scale(64) == 65000, adc_full_scale(64)
    assert adc_full_scale(65) == 65535, adc_full_scale(65)   # cap begins here
    assert adc_full_scale(9999) == 65535  # clamped to 255 steps first
    print('PASS full scale tracks integration time (11000 at ISteps=10, not 65535)')


def test_detection_saturation_is_now_visible():
    # The regression that misdetects a V2 board as V1: at ISteps=10 a pinned reading is
    # 11000, which the old hardcoded 65535 check could never see.
    ceiling = adc_full_scale(10)
    baseline, pulsed = 11000, 11000
    assert baseline >= ceiling and pulsed >= ceiling, 'saturation must be detectable'
    assert not (pulsed > baseline * 3 + 20), 'pinned readings defeat the LED-present test'
    assert not (11000 >= 65535), 'and the old check would have called this healthy'
    print('PASS a pinned detection read is detectable at ISteps=10 (was invisible)')


def _stub_read(counts):
    """Replace the low-level read with a fixed set of counts, recording the gains tried."""
    tried = []

    def fake(M, Gain, ISteps, reset):
        tried.append(Gain)
        for i, key in enumerate(['ADC0', 'ADC1', 'ADC2', 'ADC3', 'ADC4', 'ADC5']):
            sysData[M]['AS7341']['current'][key] = counts(Gain) if i == 0 else 0
        sysData[M]['AS7341']['current']['valid'] = 1
        sysData[M]['AS7341']['current']['saturated'] = 0
        sysData[M]['AS7341']['current']['fullScale'] = adc_full_scale(ISteps)
    return fake, tried


def test_autorange_steps_down_in_the_lost_band():
    # A base of 62000 is below 65535 but above the ~92% headroom line. The old rule required
    # an EXACT 65535, so this was never re-read -- it was just flagged invalid downstream.
    # Run 0 lost 49% of M4's FP1 rows and 57% of M0's FP2 exactly this way.
    original = chibio_optics.as7341_read
    try:
        fake, tried = _stub_read(lambda g: 62000 if g >= 10 else 4000)
        chibio_optics.as7341_read = fake
        get_light('M0', ['CLEAR'], 10, 255, autorange=True)
        assert tried[0] == 10, tried
        assert min(tried) < 10, 'gain never stepped down out of the 60000-65534 band: %r' % (tried,)
        assert sysData['M0']['AS7341']['current']['ADC0'] == 4000, 'kept the hot reading'
        print('PASS auto-range steps down at the headroom line, not only at 65535')
    finally:
        chibio_optics.as7341_read = original


def test_autorange_leaves_a_healthy_reading_alone():
    original = chibio_optics.as7341_read
    try:
        fake, tried = _stub_read(lambda g: 20000)
        chibio_optics.as7341_read = fake
        get_light('M0', ['CLEAR'], 6, 255, autorange=True)
        assert tried == [6], 'a mid-scale reading must not be re-ranged: %r' % (tried,)
        print('PASS auto-range leaves a mid-scale reading untouched')
    finally:
        chibio_optics.as7341_read = original


def test_fp_guard_uses_full_scale_and_hardware_flag():
    fs = adc_full_scale(255)
    assert _fp_valid_flag(30000, 1, fs, 0) == 1
    assert _fp_valid_flag(62000, 1, fs, 0) == 0, 'hot base must still be flagged'
    assert _fp_valid_flag(0, 0, fs, 0) == 0, 'a failed read stays invalid'
    # ASAT fires before the digital counter fills, so a modest count can still be saturated.
    assert _fp_valid_flag(12000, 1, fs, 1) == 0, 'hardware saturation flag must win'
    # Same ~92% rule at a shorter integration, where 60000 is unreachable.
    short = adc_full_scale(10)
    assert _fp_valid_flag(short * 0.95, 1, short, 0) == 0
    assert _fp_valid_flag(short * 0.50, 1, short, 0) == 1
    print('PASS FP guard scales with full scale and honours the hardware flag')


def test_threshold_is_unchanged_at_the_integration_fp_uses():
    # The fraction must reproduce the previous fixed 60000 exactly for real FP reads, so this
    # is a generalisation, not a retune.
    assert round(adc_full_scale(255) * NEAR_SATURATION_FRACTION) == 60000
    print('PASS headroom threshold is still exactly 60000 counts for a 255-step read')


if __name__ == '__main__':
    test_full_scale_is_integration_dependent()
    test_detection_saturation_is_now_visible()
    test_autorange_steps_down_in_the_lost_band()
    test_autorange_leaves_a_healthy_reading_alone()
    test_fp_guard_uses_full_scale_and_hardware_flag()
    test_threshold_is_unchanged_at_the_integration_fp_uses()
    print('\nAll saturation tests passed.')
