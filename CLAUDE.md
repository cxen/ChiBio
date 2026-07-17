# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The Chi.Bio operating system: a Flask web app that controls Chi.Bio bioreactors over an I2C bus. It runs **on the device** (a BeagleBone Black), not on a dev machine — see https://chi.bio/software/. There is no linter and no build step. The product code runs only on the device, but a set of `test_*.py` files run **off-device** under `CHIBIO_MOCK_HW=1` (see [Testing off-device](#testing-off-device)).

## Running / deploying

- `cb.sh` — starts the server on the device: `gunicorn -b 192.168.7.2:5000 app:application`. Uncomment the `screen` line to run detached.
- `setup.sh` — one-time device provisioning (root SSH, networking, pip deps, builds the bundled `Adafruit_BBIO-1.2.0.tar.gz`). Run once on a fresh BeagleBone.
- Auth: set the `CHIBIO_TOKEN` env var to require an `X-Auth-Token` header (or `?token=`) on non-local POSTs. Local/private-IP requests are always allowed (see `chibio_auth.py`).

**By default you cannot run this on macOS/Linux dev machines.** Importing `app.py` triggers `setup_watchdog()` and `initialiseAll()`, which talk to GPIO/I2C hardware (`Adafruit_BBIO` for GPIO/PWM, `smbus2` for I2C — `Adafruit_GPIO` was removed) and spawn the watchdog. Setting `CHIBIO_MOCK_HW=1` swaps in a no-op GPIO and skips both, so `import app` works off-device for the tests. Edit here; run the real thing on the device.

## Architecture

The whole system is **global mutable state + threads + one serialized I2C pipe**. There is no database and no message bus; routes mutate shared dicts, long-running threads read them, the browser polls a JSON snapshot.

- **`chibio_state.py`** — the three global dicts everything shares:
  - `sysData` — per-device (`M0`–`M7`) experiment/measurement state. This is what gets `jsonify`'d to the UI, so **everything in it must be JSON-serializable**.
  - `sysDevices` — per-device I2C handles and thread bookkeeping. Deliberately **separate from `sysData`** because device handles can't be serialized.
  - `sysItems` — static hardware reference: I2C register/multiplexer addresses, watchdog pin, current `UIDevice`.
  - `lock` — the single global `threading.Lock` that serializes all bus access.
- **`app.py`** — Flask routes + the core output-control functions (`SetOutput`, `set_output_on_sync`, `set_output_target_sync`, `initialise`, `turnEverythingOff`). Routes are thin: they mutate state and kick off work in a background thread.
- **`chibio_hardware.py`** — `I2CCom` is the **single chokepoint for all I2C traffic**: it acquires `lock`, switches the multiplexer to the target device, does the read/write, retries, and disconnects. `setPWM` and the watchdog live here too.
- **`chibio_optics.py`** — AS7341 spectrometer reads (`get_light`, `get_spectrum`, `get_transmission`). `get_light`/`get_transmission` take an `autorange` flag (FP-only; OD/spectrum must NOT auto-range — see conventions).
- **`chibio_measurements.py`** — `measure_od`, `measure_fp`, `measure_temp` (build on `get_transmission` / `I2CCom`). OD/FP carry a read-`valid` flag and dark-corrected / spread values.
- **`chibio_experiment.py`** — the long-running control threads: `runExperiment` (the per-cycle main loop; does the 3× median+spread OD/FP replication), `Thermostat` (PI + MPC heater control), `PumpModulation` (duty-cycled pumps), `RegulateOD` (turbidostat), `Zigzag` (OD dithering + growth-rate estimation).
- **`chibio_control_helpers.py`** — user-editable optogenetic `CustomProgram`s (C1–C6), CSV logging (`csvData` via `csv.DictWriter`), the per-experiment metadata JSON sidecar (`writeExperimentMetadata`), and `downsample`.
- **`chibio_fluorescence.py`** — the fluorescence configuration assist: scans the sample across excitation LEDs, builds a gain-normalised excitation-emission matrix, and recommends discrete FP settings via the Stokes-shift rule (`fluorescence_scan`, `recommend_fp_settings`; route `/FluorescenceScan/<M>/<mode>`).
- **Frontend** — `templates/index.html` rendered with `sysData[UIDevice]`; `static/HTMLScripts.js` polls `/getSysdata/` over AJAX and redraws. Charts are **self-hosted uPlot** (not Google Charts), theme-aware, created once and updated via `setData()`. jQuery/Bootstrap/Popper/uPlot are vendored in `static/` (no CDNs — the UI works offline). UI → backend is one-way POSTs to the routes.

### Conventions that bite if you miss them

- **Multi-device addressing.** `M0`–`M7` are 8 reactors behind an I2C multiplexer. `M == "0"` is a sentinel meaning "the current UI device" (`sysItems['UIDevice']`) — many functions normalize it at the top.
- **Threading model.** Each actuation/experiment runs in a daemon `Thread`. Routes call `run_background(...)` so Gunicorn workers don't time out. Concurrency safety comes *entirely* from `lock` inside `I2CCom` — nothing else is synchronized.
- **Thread supersession.** Restartable threads use the `threadCount` pattern: a thread captures `currentThread = (threadCount += 1) % 100` and exits as soon as `threadCount` no longer matches it. A separate `running` flag prevents launching duplicates. Preserve both when touching these loops.
- **Watchdog = safety kill switch.** Setting `sysItems['Watchdog']['ON'] = 0` (or calling `os._exit(4)`) on repeated comms failure is intentional — it crashes hardware and software rather than letting a wedged bus drive actuators. Don't "fix" these by swallowing them.
- **Circular imports are intentional.** `app.py` imports the `chibio_*` modules at top level; those modules import back from `app` *lazily inside functions* (`from app import set_output_on_sync`). Keep new cross-calls function-local.
- **Adding a recorded value is a 2–3 place edit.** To log a new measurement you must update `initialise()` in `app.py` (create its `record` list), `csvData()` in `chibio_control_helpers.py` (add one `data[...] =` line — it uses `csv.DictWriter`, which keys each value to its column by name, so header and row can no longer drift out of length-sync), and `downsample()` if it should be downsampled.
- **Per-device calibration constants are hardware tuning, not bugs.** OD calibration factors hardcoded per `M0`–`M3` (`measure_od`, `CalibrateOD`) and LED `ScaleFactor`/quadratic OD fit reflect physical device differences. Leave the knobs; don't collapse them to one value.
- **Two LED hardware versions.** `initialise()` auto-detects LED V1 vs V2 by pulsing LEDG/LEDH and watching the spectrometer; result lands in `sysData[M]['Version']['LED']`. Output code branches on it. Anything that iterates excitation LEDs (e.g. `chibio_fluorescence.excitation_leds`) must pick the version-appropriate set — driving an absent LED is a silent no-op, not an error.
- **Sensor-read failures never put `NaN` in `sysData`.** `sysData` is `jsonify`'d to the UI (a raw `NaN` breaks the browser's `JSON.parse`) and OD feeds `RegulateOD` (which drives pumps). So a failed AS7341 read sets a per-read `valid=0` flag and keeps the last-known numeric value; **only the CSV cell becomes `NaN`** (in `csvData`), so failures stay distinguishable in analysis without endangering the live loop. See the `sensor-failure-semantics` memory.
- **AS7341 gain auto-ranging is FP-only.** `get_light(autorange=True)` is safe for FP (base/emit are read in one shot, so the emit/base ratio is gain-invariant) and records the gain used. Never enable it for OD (its gain is locked to the OD calibration constants) or `get_spectrum` (it feeds `CharacteriseDevice`, which compares raw counts across a power sweep).

### Testing off-device

There is a small suite of `test_*.py` files that run on a laptop (no BeagleBone) — the payoff of the `CHIBIO_MOCK_HW` import guard. They need only the pure-Python deps (`flask numpy smbus2 simplejson`) in a venv. Run e.g. `CHIBIO_MOCK_HW=1 python3 test_read_validity.py`. Current suite: `test_import_smoke`, `test_csv_equivalence`, `test_metadata_sidecar`, `test_read_validity`, `test_autorange`, `test_replicate`, `test_fluorescence`. They cover the pure logic (analysis, CSV schema, aggregation) that would otherwise be untestable; hardware paths still need the device. The device is verified with `device_selftest.py <label>` against a running server (safe presence scan + every I2C path); the deploy/verify loop (rsync to `/root/chibio-staging`, boot, self-test, then promote to `/root/chibio`) is in the `device-deployment` memory.
