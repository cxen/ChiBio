#!/usr/bin/env python3
"""Exercise every I2C code path against a RUNNING ChiBio server and report.

Runs on the device against 127.0.0.1 (loopback is trusted, so no token needed).
Triggers the real measurement routes for each present reactor — which cover the
full I2C method surface the smbus2 migration would touch:

  measure_temp Internal/External -> I2CCom 16-bit read (readU16)
  measure_temp IR                -> I2CCom SMBUS path   (read_word_data)
  measure_od / measure_fp        -> AS7341 reads        (write8/readU8)
  every I2CCom                   -> multiplexer switch   (write8/readRaw8)

It dumps the full /getSysdata snapshot to selftest-<label>.json so you can diff a
"before" (Adafruit_GPIO) run against an "after" (smbus2) run. Read-only w.r.t.
the experiment: it reads sensors, drives no pumps and no sustained actuation.

Usage:  python3 device_selftest.py <label>      e.g.  before  /  after
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:5000"

# Sane physical ranges — a byte-order/signature bug shows up as a gross violation
# (e.g. a byte-swapped temp of 4096, not a small drift), which is exactly what we
# want the migration to catch.
TEMP_MIN, TEMP_MAX = 5.0, 80.0


def get_sysdata():
    with urllib.request.urlopen(BASE + "/getSysdata/", timeout=10) as r:
        return json.load(r)


def post(path):
    req = urllib.request.Request(BASE + path, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def check(cond, label, detail=""):
    mark = "PASS" if cond else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -- " + detail) if detail else ""))
    return 1 if cond else 0


def measure_device(M):
    for which in ("Internal", "External", "IR"):
        post("/MeasureTemp/%s/%s" % (which, M))
    post("/MeasureOD/%s" % M)
    post("/MeasureFP/%s" % M)


def main():
    if len(sys.argv) < 2:
        print("usage: python3 device_selftest.py <label>   (e.g. before / after)")
        return 2
    label = sys.argv[1]

    try:
        sd = get_sysdata()
    except Exception as e:
        print("Could not reach the server at %s -- is it running? (%s)" % (BASE, e))
        return 2

    present = [M for M in ("M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7")
               if sd.get(M, {}).get("present") == 1]
    print("Present devices: %s" % (", ".join(present) or "NONE"))
    if not present:
        print("No present devices to test.")
        return 2

    for M in present:
        measure_device(M)
    time.sleep(3)  # measurements run in background threads; let them land.
    sd = get_sysdata()

    passed = failed = 0
    for M in present:
        d = sd[M]
        print("\n%s (OD device: %s):" % (M, d.get("OD", {}).get("device")))
        results = []
        # present flag must survive — present==0 means I2C comms failed hard.
        results.append(check(d.get("present") == 1, "device still present after reads"))
        for t in ("ThermometerInternal", "ThermometerExternal", "ThermometerIR"):
            v = d.get(t, {}).get("current")
            results.append(check(isinstance(v, (int, float)) and TEMP_MIN <= v <= TEMP_MAX,
                                 "%s in range" % t, "%.2f C" % v if isinstance(v, (int, float)) else str(v)))
        raw = d.get("OD0", {}).get("raw")
        results.append(check(isinstance(raw, (int, float)) and raw > 0,
                             "OD raw transmission > 0", str(raw)))
        for FP in ("FP1", "FP2", "FP3"):
            if d.get(FP, {}).get("ON") == 1:
                base = d[FP].get("Base")
                results.append(check(isinstance(base, (int, float)) and base > 0,
                                     "%s base signal > 0" % FP, str(base)))
        passed += sum(results)
        failed += len(results) - sum(results)

    fname = "selftest-%s.json" % label
    with open(fname, "w") as f:
        json.dump(sd, f, indent=1, sort_keys=True)

    print("\n" + "=" * 48)
    print("SUMMARY (%s): %d passed, %d failed" % (label, passed, failed))
    print("Full snapshot written to %s (diff before/after to compare readings)." % fname)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
