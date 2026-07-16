# TODO

Tracking of suggested fixes/changes/improvements for the fork, ranked by importance.
Source: post-refactor evaluation (`original_app.py` monolith vs `app.py` + `chibio_*.py`).

Ranking: **P1** = real bug / correctness · **P2** = robustness or security hardening · **P3** = cleanup / hygiene · **P4** = optional, larger.

> The two biggest robustness issues are already fixed in this fork (persistent loops replacing per-iteration thread re-spawning; `try/finally` around the I2C/CSV lock). Everything below is what remains.

## P1 — Bugs

- [x] **`CharacteriseDevice` crashes.** `app.py:668` — `Thread(target=CharacteriseDevice2, args=(M))`; `(M)` is a string, not a tuple, so it spreads into `CharacteriseDevice2('M','0')` → `TypeError`. Fixed: `args=(M,)`. (Pre-existing, carried from `original_app.py:1355`.)

## P2 — Robustness / security

- [x] **Document the two self-healing concurrency races** (mark with `ponytail:` comments, no restructure needed):
  - [x] Cross-request ordering: `SetOutputTarget`/`SetOutputOn` now run as separate background threads (`app.py:445/451`), so two rapid UI actions can execute out of order. `lock` serializes the bus, not intent. `RegulateOD` re-asserts state each cycle.
  - [x] Pump-restart TOCTOU in `set_output_target_sync` off→on (`app.py:471`): old loop can exit `running→0` after the `on` path checked `running==1`, leaving `ON==1` with no loop. Worst case = one missed pump cycle; restarted next minute.
- [x] **Auth model — secured with no loss of remote convenience** (`chibio_auth.py`):
  - [x] Trust narrowed from all private IPs to loopback + the BeagleBone USB point-to-point subnets (192.168.7.0/24, 192.168.6.0/24). A shared-LAN host is no longer auto-trusted.
  - [x] Every non-local request (view **and** control) requires the token. Fail closed: no `CHIBIO_TOKEN` set ⇒ all remote access denied.
  - [x] Convenience preserved via a cookie: load once with `?token=…`, the device sets `chibio_token` (HttpOnly, 30-day), and the browser then sends it automatically on every request — all `$.ajax` control POSTs included, **zero frontend changes**. Point-to-point USB stays zero-touch.
  - Requires `CHIBIO_TOKEN` to be exported where gunicorn launches (e.g. in `cb.sh`). One-time cost: remote users append `?token=…` on first load. Caveat: HTTP-only (no TLS), so the token is visible to anyone sniffing the wire — LAN access control, not wire encryption.

## P2 — OS re-flashing / provisioning

- [x] **Repoint apt to `archive.debian.org` in `setup.sh`** before any install. Debian 10 "buster" is EOL and left the main mirrors, so `apt-get update` 404s and the from-source Adafruit_BBIO build fails. Done: archive sources + `Check-Valid-Until false` + a `sources.list.d` sweep, inserted ahead of `apt-get update`; also added an explicit `build-essential python3-dev` install for the C-extension build.
- [x] **Golden-image capture/restore flow** documented in `make-golden-image.md` — flash once, fix, snapshot the eMMC/SD, then restore that image forever after. Removes the dependency on EOL apt at provisioning time.
- [ ] **Do NOT port to a newer mainline OS image** (decision recorded, nothing to do). The Chi.Bio Debian 10.5 / Linux 4.19 image has kernel + device-tree patches for the I2C bus, the watchdog/mux GPIOs, and PWM that are baked into the image and not published as a portable patch set; the bundled Adafruit_BBIO build is matched to that kernel. Stay on the blessed image and re-flash it.

## P3 — Cleanup / docs

- [x] **Write a README** (was an upstream stub) with installation + usage that reflect this fork's changes. Done — covers context/layout, install (golden-image + `setup.sh`), run, auth, dev/test (rsync deploy + `device_selftest.py`). Covers:
  - **Context:** fork of HarrisonSteel/ChiBio; runs *on* the BeagleBone (Debian 10.5 / Py 3.7), not a dev machine; module layout (`app.py` + `chibio_*.py`, with `original_app.py` as reference).
  - **Install:** `setup.sh` (archive.debian.org repoint, `requirements.txt` pinned deps, Adafruit_BBIO from bundled tarball); the golden-image capture/restore flow (`make-golden-image.md`) as the preferred provisioning path.
  - **Run:** `cb.sh` binds `0.0.0.0:5000` (USB + LAN); set `CHIBIO_TOKEN` (via `.chibio_token`) for auth.
  - **Access / auth:** point-to-point USB is token-free; remote/LAN needs the token — open once with `?token=…`, cookie keeps it seamless after (see `chibio_auth.py`). Note HTTP-only caveat.
  - **UI:** dark-mode toggle.
  - **Dev/test:** rsync-deploy flow (device has no `git pull`); `device_selftest.py` for before/after I2C verification; note I2C now runs on `smbus2` (Adafruit_GPIO removed), GPIO/PWM still on Adafruit_BBIO.
- [x] **Delete dead scaffolding** `resolve_device_id` / `get_device_item` (`app.py:60/67`) — defined, never called. Deleted (YAGNI; `M=="0"` normalization is already done inline where needed). Verified on device: server boots and `device_selftest.py` passes 8/8 on M0/M1.
- [x] **Remove unused `import serial`** (`app.py:20`). Done — never used anywhere (traced to the first commit, carried through the refactor); Chi.Bio is I2C-only. Also dropped `pip3 install serial` from `setup.sh` (it installed the wrong package, `serial` not `pyserial`, for this unused import).

## P4 — Optional / larger (robustness direction)

- [x] **Hardware-free import path for testing.** `CHIBIO_MOCK_HW=1` swaps in a no-op GPIO (`chibio_hardware.py`) and skips `setup_watchdog()` + `initialiseAll()` (`app.py`), so `import app` works on a laptop. Gated on the env var, not on ImportError, so the device still fails loudly if real GPIO is missing (never silently mock the watchdog). `test_import_smoke.py` is the runnable check. Verified: import succeeds off-device (20 routes, no watchdog/I2C) and refuses without the flag; device path unaffected (self-test 8/8 on M0/M1).
- [x] **Pin dependencies.** Added `requirements.txt` pinned to the device's known-good versions (verified 2026-07-14; last releases compatible with the image's Python 3.7). `setup.sh` now does `pip3 install -r requirements.txt` instead of unpinned installs. Also fixed a latent bug: `setup.sh` copied `app.py` but not the `chibio_*.py` modules, so a fresh provision of the refactor would fail to import — now copies the modules and `requirements.txt` too. Adafruit_BBIO stays a from-source tarball build (kernel-matched), not pinned via pip.
- [ ] **Retire `original_app.py`** once confident in the refactor — it's reference-only and not imported. Keep until then.

## P5 — Sensor / data / UI improvements (planned, forward-looking)

New track from the 2026-07-14 improvement review — data-quality and UI enhancements, not post-refactor cleanup. **Validate every sensor-path change with `device_selftest.py` (before/after) so readings don't silently regress.** Several of these add new recorded fields, which today means a 3-place edit (`initialise` record lists, `csvData`, `downsample`) — so land the DictWriter item (below) early to make the rest cheaper.

### Sensors / measurement (`chibio_optics.py`)
- [ ] **Auto-ranging gain on the AS7341.** On saturation (`ADC==65535`) drop gain and re-read; on very weak signal raise gain. Replaces the current print-and-continue (whose own comment doubts the saturation check works). **Record the gain actually used alongside each measurement** (transparency) — add it to the record/CSV/`getSysdata`, don't just apply it silently.
- [ ] **Dark-channel background subtraction.** The `DARK` channel is already measured in `get_spectrum`/`get_light` and thrown away. Subtract it from OD/FP. **Save BOTH raw and dark-corrected values** — keep raw, add corrected fields; never overwrite raw.
- [x] **No fake fallback values.** `get_light` no longer fabricates `ADC0=1`/rest`=0` on a double read-failure; it sets a per-read `valid=0` flag and keeps the last-known values. The flag propagates to `OD['valid']`/`FP['valid']` (`measure_od`/`measure_fp`); `csvData` records `NaN` for those cells when invalid, so failures are distinguishable in analysis. **`sysData` stays numeric** so the UI JSON and `RegulateOD` never see NaN (per the sensor-failure-semantics decision). Failure branch covered off-device by `test_read_validity.py` (fault injection); success path verified on hardware (self-test 8/8, live `valid=1`, `getSysdata` serializes cleanly). No CSV column drift.
- [ ] **Replicate + median for OD/FP.** Take ~3 flashes per measurement, record the median as the value, **and record the spread/error** (std dev or min–max) so measurement noise is captured, not discarded.

### Data collection (`chibio_control_helpers.py`)
- [x] **CSV via `csv.DictWriter`.** Replaced the parallel `fieldnames`/`row` lists with a single ordered `data` dict + `csv.DictWriter`. Column order/names preserved exactly (43 columns). Adding a field is now one `data[...] =` line; header/row can't drift. Verified byte-identical to the old lists via `test_csv_equivalence.py` (off-device, both FP on/off branches); imports cleanly on device Python 3.7.3. CLAUDE.md convention note updated.
- [x] **Per-experiment metadata sidecar.** `writeExperimentMetadata(M)` writes `<startTime>_<M>_meta.json` next to the CSV at experiment start (`ExperimentStartStop`, `cycles==0` only): device ID, LED hardware version, OD device+gain+calibration constants, per-FP gain/bands, integration steps, software git hash (`git rev-parse HEAD`, graceful `unknown` fallback), start time, and per-column units. `test_metadata_sidecar.py` validates structure and asserts `column_units` covers exactly the 43 CSV columns (drift guard). Verified off-device and on device Python 3.7; server boots + self-test 8/8. (Live sidecar write on experiment start not exercised on hardware — would drive pumps/heater; covered by the off-device test.)

### GUI (`templates/index.html`, `static/`)
- [ ] **Self-host Bootstrap + the charting lib (drop CDNs).** UI currently degrades/breaks offline (there's a `TitleFailure()` fallback for the CDN logo). Bundle as local static files so the device works standalone/isolated.
- [ ] **Replace Google Charts with uPlot** (self-hosted). Kills the "destroy + rebuild the whole chart every 2 s to avoid a memory leak" hack. uPlot (~40 KB, canvas) is built for fast live time-series on weak hardware and updates incrementally. Decided 2026-07-14 — uPlot, no alternatives. This is the concrete charting choice for the self-hosting item above.
