#!/usr/bin/env python3
"""Exercise every I2C code path against a RUNNING ChiBio server and report.

Runs on the device against 127.0.0.1 (loopback is trusted, so no token needed).
/getSysdata returns only the CURRENT UI device, so this switches to each present
reactor with /changeDevice, triggers the real measurement routes, and reads the
decoded values back. Between them the measurements cover the full I2C method
surface the smbus2 migration would touch:

  measure_temp Internal/External -> I2CCom 16-bit read (readU16)   [migration-affected]
  measure_temp IR                -> I2CCom SMBUS path (read_word_data) [already smbus2 -> control]
  measure_od / measure_fp        -> AS7341 reads (write8/readU8)   [migration-affected]
  every I2CCom                   -> multiplexer switch (write8/readRaw8) [migration-affected]

Dumps each device's /getSysdata snapshot to selftest-<label>.json so a "before"
(Adafruit_GPIO) run can be diffed against an "after" (smbus2) run. Read-only
w.r.t. the experiment: reads sensors, drives no pumps and no sustained actuation.
It does briefly switch the UI device (the GUI view will hop between reactors) and
restores the original at the end.

Usage:  python3 device_selftest.py <label>      e.g.  before  /  after
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:5000"
ALL_M = ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7"]
TEMP_MIN, TEMP_MAX = 5.0, 80.0  # a byte-order bug shows as a gross violation, not drift


def gs():
    with urllib.request.urlopen(BASE + "/getSysdata/", timeout=10) as r:
        return json.load(r)


def post(path):
    req = urllib.request.Request(BASE + path, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def check(cond, label, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", label,
                           (" -- " + detail) if detail else ""))
    return bool(cond)


def num(v):
    return v if isinstance(v, (int, float)) else None


def main():
    if len(sys.argv) < 2:
        print("usage: python3 device_selftest.py <label>   (e.g. before / after)")
        return 2
    label = sys.argv[1]

    try:
        start_id = gs().get("DeviceID")
    except Exception as e:
        print("Could not reach the server at %s -- is it running? (%s)" % (BASE, e))
        return 2

    # SAFELY discover present reactors. The top-level 'present' flag DEFAULTS to 1
    # for un-scanned devices, and measuring an absent device trips the intended
    # panic/watchdog kill (os._exit) in I2CCom. So run the real scan first — it
    # probes only the internal thermometer, the one device allowed to fail
    # gracefully (sets present=0) instead of panicking — then trust presentDevices.
    post("/scanDevices/all")
    time.sleep(12)  # scan runs in the background; absent devices retry before giving up.
    pd = gs().get("presentDevices", {})
    present = [M for M in ALL_M if pd.get(M) == 1]
    print("Present devices (from scan): %s" % (", ".join(present) or "NONE"))
    if not present:
        print("Scan found no connected reactors; nothing to measure.")
        return 2

    passed = failed = 0
    snapshots = {}
    for M in present:
        post("/changeDevice/" + M)
        for which in ("Internal", "External", "IR"):
            post("/MeasureTemp/%s/%s" % (which, M))
        post("/MeasureOD/" + M)
        post("/MeasureFP/" + M)
        time.sleep(3)  # measurements run in background threads; let them land.
        d = gs()
        snapshots[M] = d

        print("\n%s (OD device: %s):" % (M, d.get("OD", {}).get("device")))
        res = []
        res.append(check(d.get("present") == 1, "device still present after reads"))
        # Migration-affected 16-bit reads:
        for t in ("ThermometerInternal", "ThermometerExternal"):
            v = num(d.get(t, {}).get("current"))
            res.append(check(v is not None and TEMP_MIN <= v <= TEMP_MAX,
                             "%s in range" % t, ("%.2f C" % v) if v is not None else "n/a"))
        # Migration-affected AS7341 read:
        raw = num(d.get("OD0", {}).get("raw"))
        res.append(check(raw is not None and raw > 0, "OD raw transmission > 0", str(raw)))
        for FP in ("FP1", "FP2", "FP3"):
            if d.get(FP, {}).get("ON") == 1:
                b = num(d[FP].get("Base"))
                res.append(check(b is not None and b > 0, "%s base signal > 0" % FP, str(b)))
        # IR uses the smbus path (unaffected by the migration) -> informational only.
        ir = num(d.get("ThermometerIR", {}).get("current"))
        print("  [INFO] ThermometerIR (smbus control): %s" % (("%.2f C" % ir) if ir is not None else "n/a"))

        passed += sum(res)
        failed += len(res) - sum(res)

    # Restore the original UI device so the GUI returns to where it was.
    for M in ALL_M:
        post("/changeDevice/" + M)
        if gs().get("DeviceID") == start_id:
            break

    fname = "selftest-%s.json" % label
    with open(fname, "w") as f:
        json.dump(snapshots, f, indent=1, sort_keys=True)

    print("\n" + "=" * 52)
    print("SUMMARY (%s): %d passed, %d failed" % (label, passed, failed))
    print("Per-device snapshot written to %s (diff before/after to compare readings)." % fname)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
