#!/usr/bin/env python3
"""Off-device unit test for the FP near-saturation guard in measure_fp.

A near-saturated CLEAR base makes the emit/base ratio untrustworthy (base compresses
toward the 16-bit ceiling), so the read must be flagged invalid — same validity/NaN
contract as a comms failure. get_light's autorange only retries on an EXACT 65535, so
this guard catches the near-ceiling bases that slip through (measured on a dense culture:
277/1012 FP cycles > 60000, 6 pinned at >=65000).

    CHIBIO_MOCK_HW=1 python3 test_fp_saturation.py
"""
import os
assert os.environ.get('CHIBIO_MOCK_HW'), "run with CHIBIO_MOCK_HW=1 (chibio_measurements imports the hardware layer)"

from chibio_measurements import _fp_valid_flag, _FP_BASE_NEAR_SATURATION

# healthy read, base well below the ceiling -> valid
assert _fp_valid_flag(42818, 1) == 1, "typical mid-range base should stay valid"

# near-saturation: base above the threshold -> invalid even though the AS7341 read 'succeeded'
assert _fp_valid_flag(65259, 1) == 0, "observed real-run max (65259) must flag invalid"
assert _fp_valid_flag(_FP_BASE_NEAR_SATURATION, 1) == 0, "threshold is inclusive (>=)"
assert _fp_valid_flag(_FP_BASE_NEAR_SATURATION - 1, 1) == 1, "just below threshold stays valid"

# a comms failure (as7341 valid=0) wins regardless of base value
assert _fp_valid_flag(1000, 0) == 0, "propagate an upstream invalid read"
assert _fp_valid_flag(65535, 0) == 0, "both conditions invalid -> invalid"

# boundary sanity: 0 base (e.g. CLEAR-as-baseband edge case) is not 'saturated'
assert _fp_valid_flag(0, 1) == 1, "zero base is not saturation (handled elsewhere in measure_fp)"

print("PASS: FP near-saturation guard flags near-ceiling bases and propagates comms failures")
