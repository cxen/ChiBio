# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

The Chi.Bio operating system: a Flask web app that controls Chi.Bio bioreactors over an I2C bus. It runs **on the device** (a BeagleBone Black), not on a dev machine — see https://chi.bio/software/. There are no tests, no linter, and no build step.

## Running / deploying

- `cb.sh` — starts the server on the device: `gunicorn -b 192.168.7.2:5000 app:application`. Uncomment the `screen` line to run detached.
- `setup.sh` — one-time device provisioning (root SSH, networking, pip deps, builds the bundled `Adafruit_BBIO-1.2.0.tar.gz`). Run once on a fresh BeagleBone.
- Auth: set the `CHIBIO_TOKEN` env var to require an `X-Auth-Token` header (or `?token=`) on non-local POSTs. Local/private-IP requests are always allowed (see `chibio_auth.py`).

**You cannot run this on macOS/Linux dev machines.** Importing `app.py` triggers `initialiseAll()`, which talks to GPIO/I2C hardware (`Adafruit_BBIO`, `Adafruit_GPIO`, `smbus2`) and spawns the watchdog. Edit here; run on the device.

## Architecture

The whole system is **global mutable state + threads + one serialized I2C pipe**. There is no database and no message bus; routes mutate shared dicts, long-running threads read them, the browser polls a JSON snapshot.

- **`chibio_state.py`** — the three global dicts everything shares:
  - `sysData` — per-device (`M0`–`M7`) experiment/measurement state. This is what gets `jsonify`'d to the UI, so **everything in it must be JSON-serializable**.
  - `sysDevices` — per-device I2C handles and thread bookkeeping. Deliberately **separate from `sysData`** because device handles can't be serialized.
  - `sysItems` — static hardware reference: I2C register/multiplexer addresses, watchdog pin, current `UIDevice`.
  - `lock` — the single global `threading.Lock` that serializes all bus access.
- **`app.py`** — Flask routes + the core output-control functions (`SetOutput`, `set_output_on_sync`, `set_output_target_sync`, `initialise`, `turnEverythingOff`). Routes are thin: they mutate state and kick off work in a background thread.
- **`chibio_hardware.py`** — `I2CCom` is the **single chokepoint for all I2C traffic**: it acquires `lock`, switches the multiplexer to the target device, does the read/write, retries, and disconnects. `setPWM` and the watchdog live here too.
- **`chibio_optics.py`** — AS7341 spectrometer reads (`get_light`, `get_spectrum`, `get_transmission`).
- **`chibio_measurements.py`** — `measure_od`, `measure_fp`, `measure_temp` (build on `get_transmission` / `I2CCom`).
- **`chibio_experiment.py`** — the long-running control threads: `runExperiment` (the per-cycle main loop), `Thermostat` (PI + MPC heater control), `PumpModulation` (duty-cycled pumps), `RegulateOD` (turbidostat), `Zigzag` (OD dithering + growth-rate estimation).
- **`chibio_control_helpers.py`** — user-editable optogenetic `CustomProgram`s (C1–C6), CSV logging (`csvData`), and `downsample`.
- **Frontend** — `templates/index.html` rendered with `sysData[UIDevice]`; `static/HTMLScripts.js` polls `/getSysdata/` over AJAX and redraws. UI → backend is one-way POSTs to the routes.
- **`original_app.py`** — the pre-refactor V1.0 monolith (~2300 lines, no `chibio_` imports), kept for reference. Not imported anywhere. Don't edit it for live changes; change the modules.

### Conventions that bite if you miss them

- **Multi-device addressing.** `M0`–`M7` are 8 reactors behind an I2C multiplexer. `M == "0"` is a sentinel meaning "the current UI device" (`sysItems['UIDevice']`) — many functions normalize it at the top.
- **Threading model.** Each actuation/experiment runs in a daemon `Thread`. Routes call `run_background(...)` so Gunicorn workers don't time out. Concurrency safety comes *entirely* from `lock` inside `I2CCom` — nothing else is synchronized.
- **Thread supersession.** Restartable threads use the `threadCount` pattern: a thread captures `currentThread = (threadCount += 1) % 100` and exits as soon as `threadCount` no longer matches it. A separate `running` flag prevents launching duplicates. Preserve both when touching these loops.
- **Watchdog = safety kill switch.** Setting `sysItems['Watchdog']['ON'] = 0` (or calling `os._exit(4)`) on repeated comms failure is intentional — it crashes hardware and software rather than letting a wedged bus drive actuators. Don't "fix" these by swallowing them.
- **Circular imports are intentional.** `app.py` imports the `chibio_*` modules at top level; those modules import back from `app` *lazily inside functions* (`from app import set_output_on_sync`). Keep new cross-calls function-local.
- **Adding a recorded value is a 2–3 place edit.** To log a new measurement you must update `initialise()` in `app.py` (create its `record` list), `csvData()` in `chibio_control_helpers.py` (add one `data[...] =` line — it uses `csv.DictWriter`, which keys each value to its column by name, so header and row can no longer drift out of length-sync), and `downsample()` if it should be downsampled.
- **Per-device calibration constants are hardware tuning, not bugs.** OD calibration factors hardcoded per `M0`–`M3` (`measure_od`, `CalibrateOD`) and LED `ScaleFactor`/quadratic OD fit reflect physical device differences. Leave the knobs; don't collapse them to one value.
- **Two LED hardware versions.** `initialise()` auto-detects LED V1 vs V2 by pulsing LEDG/LEDH and watching the spectrometer; result lands in `sysData[M]['Version']['LED']`. Output code branches on it.
