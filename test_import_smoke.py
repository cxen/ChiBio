#!/usr/bin/env python3
"""Off-device smoke test: `import app` must succeed on a laptop under CHIBIO_MOCK_HW,
without touching GPIO/I2C or starting the watchdog.

Run anywhere the pip deps are installed (flask, numpy, smbus2, simplejson) — no
BeagleBone, no Adafruit_BBIO:

    CHIBIO_MOCK_HW=1 python3 test_import_smoke.py
"""
import os

assert os.environ.get('CHIBIO_MOCK_HW'), \
    "set CHIBIO_MOCK_HW=1 first, or this tries to import Adafruit_BBIO and fails off-device"

import app  # noqa: E402  -- the whole point is that this line works off-device

# Flask app object exists and routes are registered (module-level code ran).
assert app.application.name == 'app'
rules = {r.rule for r in app.application.url_map.iter_rules()}
assert '/getSysdata/' in rules, "expected control routes to be registered, got: %s" % sorted(rules)

# The mock GPIO is in place and inert (no watchdog thread was started).
assert not app.sysItems['Watchdog'].get('thread'), "watchdog must NOT start under mock hardware"

print("PASS: import app succeeded off-device (%d routes, no watchdog, no I2C)" % len(rules))
