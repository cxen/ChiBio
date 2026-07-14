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

## P3 — Cleanup

- [ ] **Delete dead scaffolding** `resolve_device_id` / `get_device_item` (`app.py:62/69`) — defined, never called. Or wire them in as the input validation they look intended for.
- [x] **Remove unused `import serial`** (`app.py:20`). Done — never used anywhere (traced to the first commit, carried through the refactor); Chi.Bio is I2C-only. Also dropped `pip3 install serial` from `setup.sh` (it installed the wrong package, `serial` not `pyserial`, for this unused import).

## P4 — Optional / larger (robustness direction)

- [ ] **Hardware-free import path for testing.** Importing `app.py` runs `initialiseAll()` and touches GPIO/I2C, so nothing can be tested off-device. A guard (env var / mock bus) to allow `import app` on a laptop would unlock smoke tests.
- [x] **Pin dependencies.** Added `requirements.txt` pinned to the device's known-good versions (verified 2026-07-14; last releases compatible with the image's Python 3.7). `setup.sh` now does `pip3 install -r requirements.txt` instead of unpinned installs. Also fixed a latent bug: `setup.sh` copied `app.py` but not the `chibio_*.py` modules, so a fresh provision of the refactor would fail to import — now copies the modules and `requirements.txt` too. Adafruit_BBIO stays a from-source tarball build (kernel-matched), not pinned via pip.
- [ ] **Retire `original_app.py`** once confident in the refactor — it's reference-only and not imported. Keep until then.
