#!/usr/bin/env python3
"""Off-device unit test for the replicate median/spread helper used to aggregate the
3-flash OD/FP measurements.

    CHIBIO_MOCK_HW=1 python3 test_replicate.py
"""
import os
assert os.environ.get('CHIBIO_MOCK_HW'), "run with CHIBIO_MOCK_HW=1 (chibio_experiment imports the hardware layer)"

from chibio_experiment import _median_and_spread

# odd count: median is the middle, resists the outlier
med, spread = _median_and_spread([0.40, 0.42, 9.9])   # 9.9 is an outlier flash
assert med == 0.42, "median of 3 should be the middle value, got %r" % med
assert abs(spread - (9.9 - 0.40)) < 1e-9, "spread = max - min"

# a mean would have been dragged to ~3.57 by the outlier; the median is not
assert med < 1.0, "median must resist the outlier a mean would not"

# even count: average of the two middles
med, spread = _median_and_spread([1.0, 2.0, 3.0, 4.0])
assert med == 2.5 and spread == 3.0

# single read: median is itself, zero spread
med, spread = _median_and_spread([7.0])
assert med == 7.0 and spread == 0.0

print("PASS: median/spread correct for odd/even/singleton and robust to outliers")
