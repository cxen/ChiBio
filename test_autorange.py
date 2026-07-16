#!/usr/bin/env python3
"""Off-device test for AS7341 gain auto-ranging (get_light autorange=True). Injects a
fake as7341_read whose ADC value depends on the gain it's called with, and checks the
loop steps the gain toward a usable signal and records it -- and that autorange=False
(the OD path) never changes the gain, so OD's calibrated gain is safe.

    CHIBIO_MOCK_HW=1 python3 test_autorange.py
"""
import os
assert os.environ.get('CHIBIO_MOCK_HW'), "run with CHIBIO_MOCK_HW=1"

import chibio_state
import chibio_optics
from chibio_optics import get_light

M = 'M0'
sd = chibio_state.sysData[M]


def fake_read(Mx, Gain, ISteps, reset):
    # Only ADC0 carries signal (we request a single channel). Saturated at high gain,
    # good in the middle, weak at low gain -- a monotonic response to gain.
    if Gain >= 8:
        v = 65535           # saturated
    elif Gain >= 5:
        v = 30000           # good
    else:
        v = 100             # weak
    for i in range(6):
        sd['AS7341']['current']['ADC%d' % i] = v if i == 0 else 0


chibio_optics.as7341_read = fake_read

# 1. saturation: start at max gain -> drops until not saturated (lands at 7 with v=30000)
get_light(M, ['CLEAR'], 10, 255, autorange=True)
assert sd['AS7341']['current']['gain'] == 7, "should drop to first non-saturated gain, got %s" % sd['AS7341']['current']['gain']
assert sd['AS7341']['current']['ADC0'] == 30000

# 2. weak: start low -> raises until signal is usable (lands at 5)
get_light(M, ['CLEAR'], 2, 255, autorange=True)
assert sd['AS7341']['current']['gain'] == 5, "should raise to first usable gain, got %s" % sd['AS7341']['current']['gain']
assert sd['AS7341']['current']['ADC0'] == 30000

# 3. autorange OFF (the OD path): gain stays exactly as requested even when saturated
get_light(M, ['CLEAR'], 10, 255, autorange=False)
assert sd['AS7341']['current']['gain'] == 10, "autorange=False must not change the gain (OD calibration safety)"
assert sd['AS7341']['current']['ADC0'] == 65535, "no re-read -> stays saturated"

print("PASS: auto-range drops on saturation (10->7), raises on weak signal (2->5), and is inert when off")
