# ChiBio

The Chi.Bio operating system: a Flask web app that controls Chi.Bio bioreactors
over an I2C bus. It runs **on the device** (a BeagleBone Black), not on a dev
machine — see https://chi.bio/software/.

This is a fork of [HarrisonSteel/ChiBio](https://github.com/HarrisonSteel/ChiBio),
refactored and hardened. The original single-file `app.py` (~2300 lines) was split
into the modules below and retired; it remains in git history if ever needed.

## What's different in this fork

- **Modular layout.** The monolith is split into `app.py` (Flask routes + output
  control) plus focused `chibio_*.py` modules (state, hardware/I2C, optics,
  measurements, experiment loops, control helpers). See `CLAUDE.md` for the full
  architecture map.
- **Robustness fixes.** Long-running control loops are persistent threads instead
  of being re-spawned every iteration; the I2C/CSV lock is released via
  `try/finally`; a pre-existing `CharacteriseDevice` crash is fixed.
- **Token auth** for remote access (see below), with zero-touch USB access preserved.
- **I2C on `smbus2`.** The device layer was migrated off `Adafruit_GPIO` to a small
  `smbus2` wrapper in `chibio_hardware.py`. GPIO/PWM still use `Adafruit_BBIO`.
- **Pinned dependencies** (`requirements.txt`) and an EOL-safe provisioning path.
- **UI:** a dark-mode toggle.

> **You cannot run this on a macOS/Linux dev machine.** Importing `app.py` triggers
> `initialiseAll()`, which talks to GPIO/I2C hardware and spawns the watchdog.
> Edit on your machine; run on the device.

## Layout

- `app.py` — Flask routes and the core output-control functions.
- `chibio_state.py` — the shared global dicts (`sysData`, `sysDevices`, `sysItems`) and the global `lock`.
- `chibio_hardware.py` — `I2CCom`, the single chokepoint for all I2C traffic; PWM; watchdog.
- `chibio_optics.py` / `chibio_measurements.py` — AS7341 spectrometer reads; OD/FP/temperature.
- `chibio_experiment.py` — the long-running control threads (main loop, thermostat, pumps, turbidostat, zigzag).
- `chibio_control_helpers.py` — user-editable optogenetic programs, CSV logging, downsampling.
- `templates/` + `static/` — the browser UI (polls `/getSysdata/` over AJAX).

## Install (on the BeagleBone)

Runs on the Chi.Bio Debian 10.5 / Linux 4.19 image with Python 3.7. Two paths:

1. **Golden image (preferred).** Flash once, provision once, then snapshot the
   eMMC/SD and restore that image forever after. See `make-golden-image.md`. This
   removes the dependency on EOL apt at provisioning time.
2. **`setup.sh` (fresh provision).** Repoints apt at `archive.debian.org` (Debian 10
   "buster" is EOL and left the main mirrors), installs the pinned deps from
   `requirements.txt`, builds the bundled `Adafruit_BBIO-1.2.0.tar.gz` from source
   against the baked kernel, and copies `app.py` + the `chibio_*.py` modules,
   `static/`, and `templates/` into `~/chibio`. Run once on a fresh board.

`Adafruit_BBIO` is intentionally not in `requirements.txt` — it is kernel-matched
and built from the tarball, not installed from PyPI.

## Run

`./cb.sh` starts the server:

```
gunicorn -b 0.0.0.0:5000 app:application
```

Binding `0.0.0.0` serves the UI on **both** the USB point-to-point link and the LAN.
Uncomment the `screen` line in `cb.sh` to run detached.

## Access / auth

Set `CHIBIO_TOKEN` to require an `X-Auth-Token` header (or `?token=`) on remote
requests. `cb.sh` reads it from a gitignored `.chibio_token` file next to the script
(root-only, `600`); with no token set, all remote access is denied (fail closed).

- **USB point-to-point** (192.168.7.x / 192.168.6.x) and loopback are trusted — no token needed.
- **Remote / LAN**: open once with `?token=…`. The device sets an HttpOnly `chibio_token`
  cookie (30-day), and the browser then sends it automatically on every request,
  including all control POSTs — no per-request token handling in the UI.

Caveat: HTTP-only (no TLS), so the token is visible to anyone sniffing the wire.
This is LAN access control, not wire encryption. See `chibio_auth.py`.

## Development / testing

The device run dir is a git checkout, but it is **not** updated via `git pull` — the
board doesn't fetch from GitHub. Deploy by `rsync` from your machine:

```
rsync -az --delete \
  --exclude='.git' --exclude='.DS_Store' --exclude='.chibio_token' \
  --exclude='.claude' --exclude='selftest-*.json' \
  -e ssh ./ <device>:/root/chibio/
```

Always exclude `.chibio_token` (or `--delete` wipes the device's secret) and the
`selftest-*.json` artifacts.

`device_selftest.py <label>` exercises every I2C code path against a running server
on the device and dumps a per-device snapshot to `selftest-<label>.json`, so a
"before" run can be diffed against an "after" run. Use it to confirm sensor-path
changes don't silently regress readings. It safely discovers connected reactors
first (via `/scanDevices/all` + `presentDevices`) rather than measuring absent
devices, which would trip the watchdog kill.

There are no unit tests, no linter, and no build step — the code only runs on
hardware.
