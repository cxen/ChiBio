# TODO

Tracking of suggested fixes/changes/improvements for the fork, ranked by importance.
Source: post-refactor evaluation (`original_app.py` monolith vs `app.py` + `chibio_*.py`).

Ranking: **P1** = real bug / correctness · **P2** = robustness or security hardening · **P3** = cleanup / hygiene · **P4** = optional, larger.

---

## ▶ START HERE — state of the rig, 2026-08-13

**Read `INVARIANTS.md` first.** It is the operational rulebook: what happens when you touch
hardware, how to write watcher scripts that don't kill their own shell, the single-owner rule,
and which readings lie. Nearly every rule in it was learned by breaking something on 2026-08-11/12.

**Hardware: four reactors, not five.** The **M4 reactor unit is faulty and retired** — it pulls
down the shared I²C bus and prevents the whole rig from booting. Localised to the unit itself
(cable, connector, controller channel and power each excluded; the fault followed the unit to
port T7). M0–M3 verified healthy, `device_selftest.py` **16/16**. Fault report ready to send:
`docs/m4-fault-report-labmaker.md`, email draft `docs/m4-email-draft.md`.

**Run 0 is done.** 13 h, five reactors, WT in four plus a sterile blank. Archived and
md5-verified to `~/chibio-run0-2026-08-11/`. Full narrative, timings and results in
`labnotes.md`. Headline results:
- **Chi.Bio ↔ cuvette OD scale = 2.81 ± 0.22 (CV 7.7%)** across M0/M1/M4 at one density.
  Provisional — the 6–8 point dilution series (§7.1 of the audit) is still the deciding test.
- µ ≈ 0.78–0.84 /h (t_d 50–53 min) on the two clean reactors; **M0 grew at half that and its
  cause is unexplained** — see `INVARIANTS.md` §6 for two mechanisms already ruled out.
- The FP gain change (512× → 32×) took the CLEAR base from 34–60k to 3.5–8.5k and **eliminated
  all NaN losses** (previously 24–57% of rows).

**Nothing is running.** Server up on `/root/chibio`, M0–M3 present, all outputs off, laser
targets at 0.5. **Re-blank before the next run** ([[od-blanking]]) — blanks are RAM-only and the
deploy restarted the worker.

**The code backlog below is cleared, shipped and pushed.** `master` = Mac = device =
`origin/master` = **`7b3d268`**. `device_selftest.py` **16/16** on production, off-device suite
**13/13**. The `fix/concurrency-and-saturation` and `docs/literature-audit-rev2` branches were
fast-forwarded into `master` and deleted; nothing is outstanding.

### Next actions, in priority order

All four live-run defects, all four audit defects, and three more found while fixing them
(a rapid-command soft-lock, and two in `CharacteriseDevice`) are done and on the device. What
remains is bench work plus the one diagnosis that instrumentation now has to catch in the act.

**Adversarial hardware test, 2026-08-12 22:12–22:41 (4 reactors, real cultures, FP1 on at x10).**
A `FluorescenceScan` was fired at `M0` **timed to hit mid-measurement** (poll `OD['Measuring']`,
fire on the transition) so every scan was a guaranteed collision — the 2026-08-11 scenario, on
demand rather than by luck. Two runs, 6 collisions total:

| | Run 0 (before) | This test (after) |
|---|---|---|
| Experiment thread killed | yes, once (M3, 90 min lost) | **no** — cycles advanced 3→6→9→12 through every collision |
| Corrupt OD rows (`raw==0`, unflagged) | ~1 per reactor per scan | **0 of 61 rows** |
| FP rows lost to the saturation guard at x10 | 49% of M4 FP1, 57% of M0 FP2 | **0** — autorange stepped x10 down to x6–x9, bases 10.7k–50.8k |
| Server responsiveness | soft-locked under rapid commands | worst poll **0.175 s**; 25 back-to-back POSTs in 0.56 s |

The scan now *waits* instead of corrupting: the instrumentation logged
`measurement mutex on M0 waited 20.3s (contended)` — one cycle's measurement block — which is
the mutex doing exactly its job. Raw FP emission columns carried real counts (342–1389).

**The test also found a bug the unit tests could not.** The cycle stamped `time.monotonic()`
while the watchdog compared against `time.time()`; their offset (1,786,529,500 s) flagged every
reactor stalled forever and logged an error per reactor every 20 s. Nothing was restarted only
because the `is_alive()` guard refused. The unit tests passed a synthetic `now` alongside a
synthetic stamp, so the two agreed by construction. Fixed in `8728610` by routing both sides
through one named clock (`liveness_now()` / `stamp_cycle_complete()`), with a test that calls
the real stamp and asserts the clock. **Re-verified: `stalled=0` throughout, 0 false alarms.**

1. **The `WORKER TIMEOUT` of 2026-08-12 09:30:52 is still unexplained, but both documented
   suspects are now refuted by measurement on the device:**
   - *Memory pressure / `sysData` accumulation* — **refuted.** `downsample()` bounds every record
     list at 200 (measured: 177 entries in the archived M3 dump, 60 KB total per reactor). The
     board reported 366 MB available with the server up.
   - *The 10-cycle config `.txt` dump* — **refuted.** 154 ms per dump, and **five concurrent
     dumpers delay a 1 s heartbeat by at most 170 ms** — ~1800× under the 300 s timeout. It also
     does not hold the bus lock, contrary to the note here.
   - **Leading hypothesis now: starvation on the global bus lock.** `threading.Lock` is unfair,
     and a request thread can in principle be starved indefinitely under sustained contention.
   - **Instrumented rather than guessed:** a stall watchdog dumps every thread's stack plus
     loadavg if it ever loses the CPU for 30 s, and both the bus lock and the measurement mutex
     log any wait over 10 s. The next occurrence should name its own cause.
2. **Run 1 slot design for four reactors.** The runbook is scoped for five and does not fit:
   WT at n=2 plus the sterile blank take three slots, leaving one FP arm instead of two.
   Consider **two sequential four-reactor runs** (WT×2 + sterile + mCherry, then WT×2 + sterile +
   sfGFP) — keeps every non-negotiable, costs a day. Do not put a load-bearing arm on M0 until
   its slow growth is explained.
3. **Fill the ⬜ gaps in `labnotes.md`** — needs the operator, not an agent.
4. **Promote staging → `/root/chibio`** once you are happy with it, and re-blank
   ([[od-blanking]]) before the next run.

### Corrections this work produced (claims in this file that were wrong)

- **`od_raw` already existed.** The audit's "raw OD is computed and discarded" was already
  satisfied by the dark-correction work: `od_transmission_raw` *is* `OD0['raw']`. Only the raw
  **FP emissions** were genuinely missing.
- **ASTATUS (0x94) does not work on this hardware.** The audit recommended it for "the
  saturation flag and the gain actually applied in one byte". Measured 2026-08-12 by driving the
  laser into the ADC ceiling: ASTATUS reads **0x00 at every gain** — both bits are inert — while
  **STATUS2 (0xA3)** goes 0x40 → 0x58 exactly as the ADC pins. The applied gain is therefore
  **not** recoverable from the chip; the requested/auto-ranged gain remains the only account.
- **The pump spin-wait would have made things worse.** The audit prescribed `perf_counter` + a
  spin-wait for short doses, citing "time.sleep overshoots badly at short durations on this
  hardware". Measured: on an **idle** board sleep overshoots **0.1–0.7 ms** (0.5% of a 20 ms
  dose); under 4-thread load sleep is **5–14 ms** but a spin-wait is **10–35 ms**, i.e. *worse*,
  because a spinning Python thread holds the GIL and gets descheduled on a single core. Kept
  `perf_counter` and the de-quantised `round(…,5)`; **rejected the spin-wait** and instead log
  the achieved on-time so the real dose is measured rather than assumed.

---

> The two biggest robustness issues are already fixed in this fork (persistent loops replacing per-iteration thread re-spawning; `try/finally` around the I2C/CSV lock). Everything below is what remains.

## P1 — Bugs

- [x] **`CharacteriseDevice` crashes.** `app.py:668` — `Thread(target=CharacteriseDevice2, args=(M))`; `(M)` is a string, not a tuple, so it spreads into `CharacteriseDevice2('M','0')` → `TypeError`. Fixed: `args=(M,)`. (Pre-existing, carried from `original_app.py:1355`.)

### Found by the literature/code audit, 2026-08-11 (all verified in this fork's source)

From `docs/chibio-usage-literature-review.md` rev. 2 §4.1 and §1.4. **All four fixed and
device-verified 2026-08-12** — each entry keeps its original diagnosis after the fix note, since
the diagnosis is the part worth re-reading.
**Full work order, with fixes, dependencies and suggested sequencing:
`docs/audit-2026-08-11-findings-and-actions.md`.**

- [x] **AS7341 saturation is undetectable at short integration times, and can misdetect a V2 board as V1.** *(Fixed + device-verified 2026-08-12.)* `adc_full_scale(ISteps)` = `min(65535, (ISteps+1)*(ASTEP+1))`; `ASTEP` is now **written explicitly** (0xCA/0xCB) at its reset value 999, so readings are unchanged but full scale is set rather than assumed. Every saturation check compares against the read's own ceiling, and the LED-version detection logs loudly if its ISteps=10 read pins (full scale 11,000). Verified on the device: `Version['LED']`=2 with FP3=LEDH on all four reactors after the change. `test_saturation.py`.

  *Original diagnosis:* Full scale is `(ATIME+1)×(ASTEP+1)` **capped** at 65535 (datasheet DS000504 Eq. 2) — it is not always 65535. `ASTEP` resets to 999 and this fork never writes it, so at the `ISteps=10` used by the **LED V1/V2 auto-detection** (`app.py:257–270`) the sensor saturates at **11,000 counts**, which `_ADC_SATURATED = 65535` (`chibio_optics.py:14`) and the `>=`/`==` checks at `:83`/`:176` cannot see. If a bright board pins both `Baseline` and `NewLevel`, the `NewLevel > Baseline*3+20` test silently reads "LED absent" → `Version['LED']` falls back to 1 → wrong excitation panel and no FP3 LEDE→LEDH remap on a V2 board. Upstream noticed the symptom and never diagnosed it (`chibio_optics.py:84`: *"Not sure if this saturation check above actually works correctly…"*). Fix: compute the ceiling as `min(65535, (ISteps+1)*(ASTEP+1))`, or write ASTEP explicitly.
- [x] **The chip reports saturation in hardware and we have the read commented out.** *(Fixed + device-verified 2026-08-12 — but NOT via ASTATUS; see the corrections above.)* `STATUS2` (0xA3) is read while the result is latched and folded into the `valid` flag alongside the count threshold. Verified by driving the laser into the ceiling: `saturated` reads 0 at x0 and 1 at x4–x10, exactly tracking the ADC pinning. ASTATUS reads 0x00 at every gain on this hardware and is not usable.

  *Original diagnosis:* `chibio_optics.py:72` (`STATUS2`, 0xA3). **`ASAT_ANALOG` fires *before* the digital counter fills**, so no threshold on the returned number — including `_FP_BASE_NEAR_SATURATION` — can ever see it, and that is exactly the regime a 90° scatter geometry with a bright LED at 512× gain lives in. `ASTATUS` (0x94) returns the saturation flag **and the gain actually applied**, latched with the data, in one byte. Fold into the existing `valid` flag rather than replacing the heuristic (belt and braces). Also worth a comment: `_gain_multiplier`'s nominal `0.5·2ⁿ` carries ~7% systematic error across the gain range (512× is **7.75×** the 64× response, ±6% part-to-part), which matters for gain-normalising an EEM; and the band labels are ~5 nm below the ams typicals, so the Stokes-shift rule should carry ±10 nm.
- [x] **`PumpModulation` issues duplicate `setPWM` off-pairs.** *(Fixed 2026-08-12.)* Both duplicate pairs removed: one duty cycle now issues **6** setPWM writes instead of 10. `test_pump_timing.py` counts them.

  *Original diagnosis:* `chibio_experiment.py:26–29` and `:59–62` are verbatim duplicates — 4 redundant I²C transactions per pump per cycle, each taking the global `lock` and switching the mux. With 5 reactors × 4 pumps that is real pressure on the resource whose contention causes the "Failed to recover multiplexer" crashes. One-line fix, published upstream as `alje-lab@0d395e5`.
- [x] **`PumpModulation` pump timing is biased and 10 ms-quantised.** *(Fixed 2026-08-12, with a measured correction to the prescribed fix — see the corrections above.)* Took `time.perf_counter()` and `round(…,5)`; **rejected the spin-wait** (measured worse under load). Added `pump_{1..4}_ontime_ms` CSV columns recording the ACHIEVED on-time, so the delivered dose is measured rather than assumed.

  *Original diagnosis:* `chibio_experiment.py:34/55/65–67` uses `datetime.now()` + `time.sleep(Ontime)` + `round(…,2)`. `time.sleep` overshoots badly at short durations on this hardware, so every dilution volume carries a **systematic positive bias** — a quiet quantitative error in the turbidostat, i.e. in the dilution rate growth rates are computed from. Fix (`alje-lab@5d7516e`): `time.perf_counter()`, `round(…,5)`, and a spin-wait for `Ontime < 0.5 s`; plus log the achieved on-time in ms (`59fdf0c`).
### Found during the live Run 0, 2026-08-11 evening (observed on hardware, not from the corpus)

- [x] **A `FluorescenceScan` can kill the scanned reactor's experiment thread. Most serious defect currently known.** *(Fixed 2026-08-12.)* Four parts: (a) a **per-reactor measurement mutex** (`measurement_sequence`, an RLock in `sysDevices[M]['measureLock']`) held across every drive→read→off sequence, so a scan and a cycle can no longer interleave on one reactor; (b) the cycle body is wrapped so **no exception can silently kill the loop** — it logs the traceback, restores stir, un-counts the cycle and continues; (c) an **experiment watchdog** that detects a loop which has stopped completing cycles and restarts it — refusing when the thread is still alive (blocked, not dead) or when every reactor died at once, per INVARIANTS 5; (d) `lastCycleMonotonic`/`stalled` make a frozen reading **detectable** instead of reading as live data. Stir is now re-asserted on resume in `ExperimentStartStop` too. `test_concurrency.py` (14 cases).

  *Original diagnosis:* Observed on M3: its last server-log activity was 22:22:17, during its own ladder scan; `Experiment['cycles']` then froze at 110 while M0/M1/M2/M4 ran on to 155 — **90 minutes producing no data**. Worse than the lost rows: the thread died just after `runExperiment` turned **stir OFF** for a measurement (`chibio_experiment.py:324`), and nothing restores it, so **M3 sat unstirred for ~30 min**; and `OD['current']` froze at its last computed value (1.681), which is *not* flagged — it reads as a live, plausible, stable number with a low `od_spread`. That stale value then drove a supervisor's ladder trigger over all three thresholds at once. Recovered without a server restart by `POST /Experiment/0/M3` then `/Experiment/1/M3` (cycles != 0, so `startTime` is preserved and it appends to the same CSV) **plus an explicit stir re-assert** — `ExperimentStartStop` re-enables Thermostat but not Stir. Needed: find why the thread dies (start with the scan/cycle interaction below), reset `sysDevices[M]['Experiment']['running']` in a `finally`, restore stir on restart, and **timestamp every reading so a frozen `OD['current']` is detectable** (§6.2 freshness — this is a concrete instance of it).
- [x] **A `FluorescenceScan` corrupts the scanned reactor's concurrent OD row.** *(Fixed 2026-08-12 — same mutex.)* `get_transmission` holds the reactor's measurement mutex across on→read→off, and the scan holds it per excitation LED. Verified on hardware: 25 rapid `MeasureOD` POSTs produced no `raw=0` row and left the server responsive (24 ms).

  *Original diagnosis:* Same root cause, milder symptom. Scan and cycle both drive LEDs/laser on one reactor; the global `lock` serializes individual I²C transactions but *not* the on→read→off sequences, so the scan switches the laser off between the cycle's switch-on and its read. That cycle logs `od_transmission_raw = 0`, `od_measured = 0`, `od_spread` ~1.1 against a normal ~0.005 — **and `valid` stays 1**, because the read succeeded. Not flagged anywhere; the analysis filter is `od_transmission_raw != 0`. Documented in the runbook §7.3. Proper fix is a per-reactor mutex around the whole measurement sequence, not just the bus.
- [x] **FP gain must be planned against the density the run will reach, not its starting density.** *(Fixed 2026-08-12.)* Auto-range now steps the gain down on lost **headroom** (~92% of full scale, the same line the FP guard uses) instead of only on an exact 65535 — so the whole 60000–65534 band that NaN'd 49% of M4's FP1 rows is now re-read at a usable gain rather than discarded. The guard is expressed as a fraction of the read's actual full scale, identical to 60000 counts at the 255-step integration FP uses.

  *Original diagnosis:* At the runbook's `x10` (index 10 = 512×) the CLEAR base climbed from ~6–11k at inoculation to 34–60k within two hours, and the 60000 near-saturation guard NaN'd **49% of M4's FP1 rows, 57% of M0's FP2, and 24–28% of all three on M1**. Autorange does not rescue this: it only steps down on an *exact* 65535, so the whole 60000–65534 band is lost. The sterile M2 lost nothing, confirming cell scatter as the cause. Dropping to index 6 (32×) mid-run took the base to 3.5–8.5k. Options: default the assist to a lower starting gain, make autorange trigger on the guard threshold rather than 65535, or expose a headroom-aware recommendation. Note the ratio is gain-invariant, so a mid-run gain change is safe for comparability — and `SetFPMeasurement` already logs it to the events sidecar.
- [x] **Correction to the audit's §4.3.1 exposure.** *(Recorded; the raw-emit columns landed 2026-08-12, so this is closed.)* Raw FP emissions *are* recoverable from the current CSV after all: `FP*_base` is logged as **raw counts**, `FP*_gain_used` per row, and the emissions are ratios of that base — so `emit_raw = emit_ratio × base` at a known gain. Matched-control subtraction **can** be retro-fitted to this dataset. The raw-emit column below is still worth landing (precision, and not making every analyst rediscover the identity), but it is not data-losing.

- [x] **Raw OD and raw FP emissions are computed and discarded.** *(Fixed 2026-08-12; scope corrected — `od_raw` already existed as `od_transmission_raw`.)* Added `FP{1,2,3}_emit{1,2}_raw`, the emission counts before the Clear division, carried through the same replicate/median path. Note each key is medianed independently, so `emit_raw/base` need not exactly equal the logged ratio. CSV is now 63 columns; the metadata sidecar's `column_units` covers all of them (drift-guarded by `test_metadata_sidecar.py`).

  *Original diagnosis:* Highest value-per-line change in the audit. `OD0['raw']` → an `od_raw` CSV column, and the FP emission counts *before* the Clear division → `FP{1,2,3}_emit{1,2}_raw`. Combined with a RAM-only blank ([[od-blanking]]), a mid-run restart currently changes the meaning of the OD column with no way to undo it; and matched-control subtraction **cannot be retro-fitted to data already collected** while only ratios are stored. Both are this fork's documented 2–3 place edit (`initialise()` + `csvData()` + `downsample()`) and compose with the existing `logEvent` blank records. Prior art: `zoltuz@imperial_GBS`.

### Found while fixing the above, 2026-08-12/13

- [x] **Rapid commands soft-lock the server (uncapped background threads).** *(Fixed +
  device-verified 2026-08-12.)* Every POST to a `/Measure*` or output route called
  `run_background`, which spawned an **unbounded** `Thread`. A burst of clicks therefore
  created a pile of slow (~1.6 s) threads all contending for the one global bus lock — and the
  new per-reactor measurement mutex, on its own, would have made this *worse* by converting the
  race into a queue. Two changes: manual measurement requests are now **coalesced per exact
  (reactor, measurement)** — a repeat while one is in flight is dropped, not queued — and
  `run_background` refuses past 64 live tasks with a loud log. Keyed on the *exact* measurement,
  not the reactor: an earlier per-reactor key silently dropped every distinct read after the
  first, which the device self-test caught as `ThermometerExternal = 0.00 C` on all four
  reactors. Verified on hardware: **25 back-to-back `MeasureOD` POSTs in 0.56 s**, median POST
  latency 23 ms, `/getSysdata/` answering in 24 ms immediately after, no `raw=0` row.
  Distinct from the M4 fault (M4 was healthy through Run 0) and from the 20:12:57 worker
  timeout, though all three share the single-core-plus-one-bus-lock root.
- [x] **`CharacteriseDevice` silently rescaled OD, and corrupted any concurrent experiment.**
  *(Fixed + device-verified 2026-08-13.)* Found by running the newly-guarded characterisation
  against a live experiment. Two defects, both invisible from outside:
  - The power sweep **left every LED and `LASER650` at 1.0**, the last level it visits, and never
    restored them. The blank is taken at `LASER650=0.5`, so the reactor goes on reporting OD
    against a laser at twice that power until someone re-blanks or restarts — **M0 read OD 3.17
    before characterisation and 2.60 after**, with nothing to indicate why. Targets are now saved
    up front and restored in a `finally`, so a run that dies partway cannot strand the laser.
  - Run **during** an experiment, the sweep takes `LASER650` down to zero power and a cycle
    measuring in that window logged **OD 9.99**. The per-reactor mutex makes each read atomic but
    cannot hold a *shared power target* still between them, so `/CharacteriseDevice` now returns
    **409** while an experiment is running on that reactor. Verified on the device: 409 while
    running; a clean run restores every target exactly and leaves no output on.
  - Note the scope limit this exposes: the mutex protects on→read→off **sequences**, not shared
    *setpoints*. Anything that sweeps an output's power while another thread measures the same
    reactor must decline, not just serialise.
- **Consequence for [[measurement-routes-not-reentrant]]:** the ≥5 s spacing rule is now a
  data-quality preference, not a correctness requirement — the mutex makes overlapping reads
  safe. Blanking should still space its reads, because settling time is physical.

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
- [x] **Retire `original_app.py`** — deleted 2026-07-17 once the refactor was verified on hardware and promoted to `/root/chibio`. It was reference-only and never imported; still recoverable from git history. Doc references (README, CLAUDE.md) updated.
- [x] **Simulation mode (`CHIBIO_SIM=1`, `chibio_sim.py`).** *(Built + device-verified 2026-08-11, commit `73ec675`.)* Motivated by a bare controller being unable to boot at all: with no reactors the mux at `0x74`/bus 2 never ACKs, `I2CCom` exhausts its retries and `os._exit(4)`s. `CHIBIO_MOCK_HW` was the only alternative and is unfit for UI work — it skips `initialiseAll()`, so FP `*Record` stays the int `0`, the FP LED/band/Gain fields stay `0` (blank GUI dropdowns) and `Version['LED']` stays 1 (V1 panel on a V2 board). The sim instead fakes the **bus** (`smbus2.SMBus` stand-in for multiplexer, both MCP9808s, IR thermometer, DAC, both PWM chips) plus `chibio_optics.get_light`/`get_spectrum`, and runs the real `initialiseAll()` on top — so presence scan, LED V1/V2 detection + the FP3 LEDE→LEDH remap, `measure_od`'s calibration/dark correction, `measure_fp`'s ratio + near-saturation guard, `Thermostat`, `RegulateOD`, `csvData` and the fluorescence assist all execute for real. `_transmission_counts` inverts `measure_od`'s formula so the OD it recovers is the OD the culture model holds. Behind the optics: logistic growth diluted by Pump1 (turbidostat closes the loop) and a first-order heater model. Config: `CHIBIO_SIM_{LED_VERSION,REACTORS,HOURS,SEED}`. Verified on the device — M0–M4 present / M5–M7 absent via the real scan, V2 panel with FP3 on LEDH, 12 h history, live MeasureOD/FP/Temp, a full fluorescence quick scan, and three live experiment cycles in which `downsample()` fired and the Thermostat PI drove the heater; zero tracebacks; real-mode boot still fails at the bus with no import errors. Also verified serving the full UI on macOS with no BeagleBone. `test_sim.py` covers it off-device (suite 10/10). **Not a substitute for the device** — see the hardware-first note in CLAUDE.md.

## P5 — Sensor / data / UI improvements (planned, forward-looking)

New track from the 2026-07-14 improvement review — data-quality and UI enhancements, not post-refactor cleanup. **Validate every sensor-path change with `device_selftest.py` (before/after) so readings don't silently regress.** Several of these add new recorded fields, which today means a 3-place edit (`initialise` record lists, `csvData`, `downsample`) — so land the DictWriter item (below) early to make the rest cheaper.

### Sensors / measurement (`chibio_optics.py`)
- [x] **Auto-ranging gain on the AS7341 (FP only; OD and spectrum intentionally excluded).** `get_light(autorange=True)` steps the gain down on saturation (`ADC>=65535`) and up on weak signal (max requested channel `<1000`), bounded to 4 retries, then records the gain used in `sysData['AS7341']['current']['gain']`. Applied to **FP** (`measure_fp`), where base/emit are read in one shot so the emit/base ratio is gain-invariant — the gain used is recorded per-FP (`GainUsed`, new `FP*_gain_used` CSV columns + `getSysdata`). **Not** applied to OD (its gain is locked to the OD calibration constants) or to `get_spectrum` (feeds `CharacteriseDevice`, which compares raw counts across a power sweep — a per-read gain change would break comparability). Verified: logic off-device (`test_autorange.py`: drops 10→7, raises 2→5, inert when off); on hardware FP settled at gain 10 with Base 19360 and recorded `GainUsed=10`; OD unchanged, self-test 8/8.
- [x] **Dark-channel background subtraction (OD done; FP deferred).** OD reads now request `['CLEAR','DARK']`; `measure_od` records `OD0['dark']` and `OD0['rawCorrected']` (raw − dark) alongside the untouched raw. Three CSV columns added — `od_transmission_raw`/`_dark`/`_corrected` (counts) — NaN-gated by the read-validity flag. Verified on hardware: adding DARK doesn't perturb CLEAR (M0 raw 10764, in-range vs prior runs), DARK reads a small background (~1 count), corrected computes correctly; self-test 8/8. **FP deferred:** emit values are stored as ratios (emit/base), so a proper dark correction needs the raw emit counts that aren't currently kept — bigger change, follow-up.
- [x] **No fake fallback values.** `get_light` no longer fabricates `ADC0=1`/rest`=0` on a double read-failure; it sets a per-read `valid=0` flag and keeps the last-known values. The flag propagates to `OD['valid']`/`FP['valid']` (`measure_od`/`measure_fp`); `csvData` records `NaN` for those cells when invalid, so failures are distinguishable in analysis. **`sysData` stays numeric** so the UI JSON and `RegulateOD` never see NaN (per the sensor-failure-semantics decision). Failure branch covered off-device by `test_read_validity.py` (fault injection); success path verified on hardware (self-test 8/8, live `valid=1`, `getSysdata` serializes cleanly). No CSV column drift.
- [x] **Replicate + median for OD/FP.** `runExperiment` now takes 3 flashes per measurement and records the **median** (robust to outlier reads) instead of the old 4× mean, plus the **spread** (max − min). OD: 3× `measure_od` → median feeds `RegulateOD` + CSV, `od_spread` column added. FP: 3× per active FP → median of each channel + `FP*_spread` (base-signal spread). Validity is AND-ed across the 3 reads. `_median_and_spread` helper unit-tested off-device (`test_replicate.py`: odd/even/singleton + outlier resistance). Building blocks (`measure_od`/`measure_fp`) verified on hardware (self-test 8/8) and the app boots clean; the full experiment-loop aggregation itself isn't exercised on hardware (would need a live experiment driving pumps/heater) — covered by the unit test.

### Data collection (`chibio_control_helpers.py`)
- [x] **CSV via `csv.DictWriter`.** Replaced the parallel `fieldnames`/`row` lists with a single ordered `data` dict + `csv.DictWriter`. Column order/names preserved exactly (43 columns). Adding a field is now one `data[...] =` line; header/row can't drift. Verified byte-identical to the old lists via `test_csv_equivalence.py` (off-device, both FP on/off branches); imports cleanly on device Python 3.7.3. CLAUDE.md convention note updated.
- [x] **Per-experiment metadata sidecar.** `writeExperimentMetadata(M)` writes `<startTime>_<M>_meta.json` next to the CSV at experiment start (`ExperimentStartStop`, `cycles==0` only): device ID, LED hardware version, OD device+gain+calibration constants, per-FP gain/bands, integration steps, software git hash (`git rev-parse HEAD`, graceful `unknown` fallback), start time, and per-column units. `test_metadata_sidecar.py` validates structure and asserts `column_units` covers exactly the 43 CSV columns (drift guard). Verified off-device and on device Python 3.7; server boots + self-test 8/8. (Live sidecar write on experiment start not exercised on hardware — would drive pumps/heater; covered by the off-device test.)

### Fluorescence configuration assist (explore)
- [x] **Help the user choose fluorescence settings from their sample.** Implemented in `chibio_fluorescence.py`: a scan drives each version-appropriate excitation LED, reads the emission spectrum with gain auto-ranging, and builds a gain-normalised excitation-emission matrix; `recommend_fp_settings` applies the Stokes-shift rule + a noise-floor threshold to pick the best discrete Excite LED + Emit1/Emit2 bands + gain (or none for a non-fluorescent sample). Route `/FluorescenceScan/<M>/<mode>` (quick = one power/LED, full = power sweep). Frontend panel (`index.html`/`HTMLScripts.js`) shows the recommendation + a colour-scaled EEM heatmap (scatter cells dimmed, recommended cell outlined) with **Apply → FP1/2/3** buttons that populate the FP dropdowns. Verified: analysis off-device (`test_fluorescence.py`), scan on hardware (all LEDs, EEM, LEDs left off, self-test 8/8), and the panel/heatmap/apply in a browser. Threshold + Stokes cutoff are knobs to tune against a known fluorophore.

### GUI (`templates/index.html`, `static/`)
- [x] **Self-host Bootstrap + the charting lib (drop CDNs).** Vendored jQuery 3.2.1, Bootstrap 4.0.0 (CSS+JS), Popper 1.12.9, uPlot 1.6.31 (JS+CSS) and the `CBL.png` logo into `static/`; `index.html` references them via `url_for`. No CDN dependencies remain (only the plain chi.bio hyperlink + the optional news iframe, which blanks gracefully offline). Verified: device serves the page (HTTP 200) with local assets, static files 200.
- [x] **Design tokens + contrast pass (P6 GUI polish).** Root cause of the "text invisible / frames lost / charts blend in" reports was that dark mode was a hand-written *whitelist* of `html[data-theme=dark]` overrides, while 19 frames used inline `style="border:…"` and 26 `<font color=…>` tags — inline styling beats every stylesheet rule, so those elements could never be themed (measured: dark border `#444` vs surface **1.47:1**, white LED frame on white **1.00:1**, `<font color="000000">` = literally black text on a dark panel). Replaced with one OKLCH `:root` token block (both themes), verified WCAG-AA by a contrast script: text ≥ 4.5:1, frames 3.3–4.0:1, chart series ≥ 4.1:1 (dark green went 3.44 → 6.42). `chartTheme()` now reads the tokens instead of holding a second palette; `.container` background dropped (layout ≠ surface); dead `.table` rules removed; `prefers-color-scheme` now the default (was hardcoded `light`).
- [x] **Frames, charts, controls, layout (P6).** `.panel` frames every box; channel colour moved from the frame to a `--channel` accent stripe (`.panel--ch`) so white/black channels stay visible. All 7 chart divs are `.panel.chart` with a reserved min-height, so an empty chart holds its shape. 66 inline `setAttribute("style", …)` state writes (only 3 distinct strings, 33 ids) collapsed into `setActive(id,''|'on'|'go')` + `.is-on`/`.is-go` + `aria-pressed`. uPlot legend rows (the real "plot toggles") got a pointer/hover affordance and strike-through instead of a 0.3 opacity fade. M0–M7 overlap fixed (they were `col-1` ≈21px cells holding ~34px buttons → now a 4×2 grid); `.container .row` sizes to content, fixing the `col-2`-holds-a-48px-label collisions. Theme toggle is now an in-flow sun/moon slider (`role="switch"`, reduced-motion aware) — and lives **outside** `#titlesection`, which `TitleFailure()` wipes. Verified in-browser both themes (populated + empty), all 7 off-device tests pass. **Not yet run on the device.**
- [x] **`cb.sh` prints the GUI URL.** Iterates `hostname -I`, appending `?token=` only for non-trusted IPs (`chibio_auth.py` trusts loopback + `192.168.7/6.x`), plus an SSH hint. Was documented by hand in README.
- [x] **Replace Google Charts with uPlot** (self-hosted). `drawChart2` (Google Charts, `clearChart()` every poll to dodge the memory leak) replaced by a uPlot renderer that creates each chart once and `setData()`s on updates — no per-cycle rebuild. dataviz-validated categorical palette (blue/green/magenta), recessive dashed target reference lines, crosshair+legend hover, and **dark-mode-aware** theming that re-renders on the toggle. OD chart adds the **spread band** + **dark-corrected** trace (Phase B+; backend `spreadRecord`/`correctedRecord` record lists added, downsampled). Verified in-browser (all 7 charts, light + dark) and on device (boots, self-test 8/8, new record fields present).

### P7 — GUI refinements from live-experiment observations (2026-07-17, PLANNED)

Noticed while a real experiment runs. All three are UI-only. **Each triggers the GUI design-skill sequence in CLAUDE.md when implemented** (device snapshot first, then frontend-design → better-colors → better-typography → better-ui → emil-design-eng → critical-code-reviewer). Verify in-browser in **both** themes against a real `/getSysdata/` snapshot.

- [x] **Legend shows the latest value at rest, cursor value on hover.** *(Done 2026-07-18, verified on device.)* `showLatestWhenIdle(u)` hook on every chart (`ready`/`setData`/`setCursor`): when `u.cursor.idx == null` (off-plot, or after a poll update) it calls `u.setLegend({idx: u.data[0].length-1})` to fill the value cells with the most-recent point; hovering lets uPlot's own `cursor.idx` drive them; mouse-leave reverts to latest. `setLegend` doesn't move the cursor, so no re-entrancy with the `setCursor` hook; no custom legend DOM. Verified on device with a synthetic dataset: at rest OD reads `1.244` (last point, not `--`); hovering mid-plot reads the cursor value (`0.107` at idx 24); mouse-leave reverts to `1.244`. No reflow (the reserved 8ch `tabular-nums` column already held the width).
- [x] **Legend series marker reads as a checkbox.** *(Done 2026-07-18, verified on device both themes.)* Restyled `.u-legend .u-marker` to a 14×4 rounded pill: uPlot colours the marker via an inline `border: 2px solid <stroke>` and `.uplot *` is `box-sizing:border-box`, so a 4px-tall box is entirely border → a solid colour bar in the series stroke, no JS. Verified on-device (M0, dark+light): Target=grey, OD dark-corrected=green, OD=blue pills; hide affordance (strike-through + `.u-off` dim) preserved. Also removed a dead `html[data-theme=dark] .u-marker{border-color:currentColor}` rule (inline border always beat it).
- [x] **UV Light Output panel: violet accent, not faint blue.** *(Done 2026-07-18, verified on device both themes.)* `#UVContainer` `--channel` changed `#a5e1ff` → `#A257FE` = `oklch(0.628 0.236 300)`, a blue-violet at ~hue 300 (physically right for UV, distinct from LEDB's `#0056FF`). Contrast computed **3.77:1 vs the light panel / 3.83:1 vs dark** (≥3:1 both, per the stripe convention). Verified on device: violet stripe reads clearly in both themes, distinct from the 650nm red / 623nm orange stripes.

- [x] **Per-chart log/linear y-axis toggle (natural log, base e).** *(Done 2026-07-18, verified on device both themes with a synthetic exponential OD dataset.)* Implemented **true ln (base e)**, not uPlot's native log (which is base 10/2 only): `drawUplot` plots `ln(y)` on a linear axis and formats ticks + legend back to real readings via `Math.exp`, so **the slope reads directly as μ** (per hour). Ticks land on 1-2-5 "nice" real values (`0.02/0.05/0.1/0.2/0.5/1/2…`); axis label gets a `(lnₑ)` suffix. **X/Time stays linear.** Non-positive values (blanked dips, negative growth-rate) mask to `null`. Small `ln` toggle injected above each chart, right-aligned, shared `.is-on` on-state tokens (both themes); `isLog` is in the rebuild key so a toggle forces a clean rebuild while `setData` still gets log data. Per-chart on the exponential-signal charts only: **OD (1), FP1-3 (4/5/6), Growth Rate (7)** — Temperature/Pump stay linear. Verified on device: exponential curve → straight line, clean ticks, X linear, legend exp-formatted, round-trip on/off, state persists across the theme toggle, both themes. Files: `static/HTMLScripts.js` (`chartLog`/`LOG_CHARTS`/`logSplits`/`logAxisValues`/`initLogToggles` + `drawUplot`), `templates/index.html` (`.log-toggle` CSS). Note: the Growth-Rate chart masks its frequent non-positive points in ln mode (least naturally-log of the five, included per scope choice).

- [x] **Drag-to-zoom ROI rectangle is invisible in dark mode.** *(Done 2026-07-18, verified on device both themes.)* Added `.u-select { background: var(--band); border: 1px solid var(--accent); }` in `index.html` (overrides the vendor `rgba(0,0,0,0.07)` by source order). `box-sizing:border-box` keeps the 1px border inside uPlot's inline-sized rect, so the zoom region doesn't shift; `pointer-events:none`/`position:absolute` persist via per-property cascade. Verified on device by forcing `.u-select` visible: translucent accent fill + accent border reads clearly on both the dark and light chart surfaces.

### Fluorescence assist — live-validation follow-ups (2026-07-17, PLANNED)

First validation against real fluorophores: GFP in M0, YFP in M1 (MG1655, single chromosomal copy, M9+0.2% glucose), scanned in exponential at OD ~0.34–0.40.

- [ ] **`recommend_fp_settings` is fooled by biomass autofluorescence.** Both reactors returned the *identical* recommendation `excite LEDI(550) → emit nm583/nm620`, and the reported `signal` scaled with OD (80 @ OD 0.34 on M0 vs 103 @ OD 0.40 on M1) — i.e. it locked onto green-excited cellular **autofluorescence** common to both, not the FP (GFP emits ~509/nm510, YFP ~527/nm550; neither at 583). Root cause: the Stokes-shift rule filters excitation *scatter* but not autofluorescence, and the recommender picks the strongest Stokes-valid EEM cell — which at OD ≳0.3 with dim single-copy FPs is autofluorescence. The genuine FP cells are weak: GFP LEDB(457)→nm510 ≈ 10.6, YFP LEDD(523)→nm550 ≈ 19.2. Fixes to weigh: (a) subtract a WT / no-FP autofluorescence blank (needs a control reactor — not currently available); (b) constrain/weight excitation toward the fluorophore's known band; (c) require the FP-region cell to beat the autofluor cell by a margin before recommending it; ~~(d) only trust the auto-recommendation at higher density where FP:autofluor improves~~ — **DISPROVEN 2026-07-18**: re-scanned at true plateau (OD 1.54 M0 / 1.37 M1) and it STILL recommended ex550→nm583/620, identical for both fluorophores (signal 230/258, ~equal despite different OD) — autofluorescence and scatter scale with biomass just like the FP, so density never improves the ratio. The fix must be (a)/(b)/(c), not "wait for denser". This is the "tune the Stokes cutoff + noise-floor against a known fluorophore" knob from the `sensor-failure-semantics`/fluorescence notes — now with data across three densities showing the failure mode.
- [x] **V2 has no ~488 nm LED for GFP.** *(Done 2026-07-18, verified on device.)* GFP excitation peaks ~488; the V2 set jumps 457 (LEDB) → 500 (LEDC). LEDB under-excites GFP; LEDC(500)→nm510 is only 10 nm Stokes so it's scatter-contaminated. Documented in `CLAUDE.md` (onboard-fluorescence note) and surfaced in the assist UI: a `#FluorV2Note` caveat (shown only when `Version.LED==2`, toggled in `renderFluorescence`) points out the missing ~488 nm channel and recommends LEDB→nm510 as the least-bad readout. Verified on the V2 device — note renders in the Fluorescence assist panel.
- [x] **Quick-scan read dropouts at low signal (M1).** *(Done 2026-07-18, verified on device.)* Root cause: `_emission_spectrum` ignored the AS7341 read-validity flag, so a `valid=0` dropout (which keeps the **last-known** counts, per [[sensor-failure-semantics]]) baked a stale/zero value into the EEM at the wrong gain and skewed the gain-normalisation. Fix: `_emission_spectrum` now returns `_valid` (AND of both `get_light` reads); the scan **retries** a dropout up to `_SCAN_READ_RETRIES` (2) times before accepting it, tags each EEM row with `_valid`, and prefers a valid row over any invalid one; `recommend_fp_settings` **skips `_valid==0` rows** so a dead read's counts can't be recommended. Off-device tests in `test_fluorescence.py` (D: recommender skips invalid rows; E: scan retries a transient dropout and every kept row is valid). Verified on device: live quick-scan produced 6 EEM rows all carrying `_valid=1`, LEDs left off. (Note: does not change the *autofluorescence* pick — that still needs the matched WT control; this only stops dropouts corrupting the matrix.)

- [x] **FP-config changes mid-run aren't recorded — the dataset isn't self-describing.** *(Done 2026-07-18 via option (c), verified on device.)* `logEvent(M, type, detail)` (`chibio_control_helpers.py`) appends a timestamped record to a companion **`<startTime>_<M>_events.json`** (JSON array, atomic temp+`os.replace` write under the bus lock; no-op unless an experiment is running). Wired into `SetFPMeasurement` (both branches — a slot turning on records led/base/emit/gain; turning off records `on:0`) and `CalibrateOD` (records the new OD zero, device, raw/known-OD). Each event carries `exp_time` (aligned with the CSV `exp_time` column), `wall_time`, `type`, `device`, `detail` — so a mid-run FP-band switch or OD re-blank is no longer a silent discontinuity in the per-slot CSV columns. Off-device test `test_events_log.py` (no-op when idle; JSON-array append; accumulates; atomic). Verified on device: routes stay 204 and correctly write nothing while idle; server stable. (Chose (c) over amending the CSV so the CSV schema stays fixed; pairs with [[od-blanking]] and the metadata sidecar.)

### Fluorescence quantification — literature-validated (2026-07-18)

From the usage literature review (`docs/chibio-usage-literature-review.md`). **The onboard AS7341 fluorescence is not quantitatively trustworthy for GFP-in-cells as normalized today.** The evidence, in descending strength (rev. 2 of the review, 2026-08-11): the colleagues' bioRxiv metrology paper (Sambruna/Tallarico/Cosentino Lagomarsino 2026, on the *upstream* software: fixed GFP cells indistinguishable from wild-type, S/B ≈ 1.0, while a plate reader resolved them easily); a **purpose-built 90° fluorimeter with real interference filters that failed the same way** (Fluorostat 2015 — so this is geometry, not the cheap chip); **five years of forum reports** with Steel naming filter bleed-through as the cause and giving a floor of *"<0.5% of 'very bright'"*; a QUT thesis showing the readout is **flat during turbidostat steady state** and only separates once dilution stops (i.e. the worst case is exactly the mode this rig runs in); **three groups that built per-reactor calibration layers** rather than trust it raw; and a control group that built an EKF instead, writing that in-situ fluorescence *"would eliminate the need for observers"*. Corroborating *practice* rather than measurement: the Joshi lab used the onboard channel only as a live monitor and took quantitative points offline (cytometry for sfGFP, qPCR for PCN) — they never compared the two, so this is revealed preference, not a cross-check. Root cause (confirmed by H. Steel, pers. comm. in the paper): broad-spectrum LEDs leak excitation through the emission filters → concentration-dependent background; the 90° LED–detector geometry adds a scatter peak near the excitation wavelength. These build on the deferred FP-dark-correction and the autofluorescence items above — same track, now with external corroboration. **Each GUI-facing item triggers the CLAUDE.md GUI design-skill sequence.**

- [x] **Guard Clear-channel saturation in FP normalization.** *(Implemented off-device 2026-07-18; **deployed + verified on device 2026-07-18** — staging self-test 8/8, live-fired on M0 stationary culture: with the threshold temporarily at 55000 the ~56000 CLEAR base flipped `valid=0` on every read, confirming the firing path end-to-end; restored to 60000, promoted to `/root/chibio`, prod self-test 8/8. Note: at the current cooled/settled density M0 peaks ~56000 — just under the 60000 line — so live reads sit `valid=1`; the ≥60000 regime is the warm freshly-plateaued state, already matched by the off-device test + the archived weekend CSV incidence, 277 M0 / 52 M1.)* `_fp_valid_flag(base, as7341_valid)` in `chibio_measurements.py` flags `valid=0` when the CLEAR base ≥ `_FP_BASE_NEAR_SATURATION` (60000, ~92% FS), so `csvData` logs NaN instead of a silently-corrupted ratio — same validity/NaN contract as a comms failure. Autorange only retries on an *exact* 65535, so near-ceiling bases slipped through. `test_fp_saturation.py` covers the branch off-device (7/7 suite green, no regression). Validated against the live-run CSVs: the shipped helper flags exactly the observed incidence (M0 FP3 277/689 active cycles ≈ 40% at plateau, M1 52/688) — confirming it does what the data showed. The high M0 rate is itself a signal the FP3 gain/band saturates at this density (revisit on-device). ponytail: 60000 is a fixed threshold; retune against a saturating culture if it proves off.
- [ ] **Make direct non-fluorescent-control subtraction a first-class FP mode**, over ratiometric Clear-normalization. The paper shows matched-control subtraction (same reactor) is linear with near-zero intercept, where ratiometric breaks at both ends. This is the concrete form of the deferred "FP dark correction" (needs the raw emit counts, currently stored only as emit/base ratios — see [[sensor-failure-semantics]]). Control must be same-device or cross-device calibrated.
- [ ] **Enforce a minimum ex/em separation** in `recommend_fp_settings` to avoid the scatter peak (90° geometry) — dovetails with the autofluorescence-margin fix above. The Stokes-shift rule already leans this way; make the cutoff explicit. **Finding 2026-07-18 (off-device, real M1 EEM):** min-separation alone does NOT fix the autofluorescence pick — the current recommender chooses `ex550→nm583` (autofluor ridge, 33 nm shift, already Stokes-valid) over the true `ex523→nm550` YFP cell (4× weaker), and no single-reactor heuristic (bigger Stokes floor, margin-over-floor, peak-localization) reliably separates a dim FP from the ridge without over-filtering legit FPs. **Confirmed this needs the matched non-fluorescent-control subtraction above, which needs a WT/blank reactor set up on-device.** Deliberately NOT shipping a heuristic that would give false confidence. Do with the Monday control experiment.
- [ ] **GUI: warn when expected signal is likely sub-detectable** (GFP-in-cells is near/below the floor) and suggest a sensitive-instrument pre-check. Raising gain/LED power does **not** help — it scales signal and background together (paper Fig S4), so the UI shouldn't imply it will.
- [ ] **Per-device fluorescence calibration constants** (a bead-based reference stored per reactor), the prerequisite for any cross-device fluorescence comparison. Inter-device σ persists after normalization (net-signal / σ_device ≈ 3.3, not reliably above threshold). *(Justified by the paper directly, not — as previously written — "exactly like the per-M0–M3 OD factors": those `CF` constants are inherited dead code. The live in-repo precedent is the per-reactor blank `OD0['target']` via `CalibrateOD`.)* **Two published recipes now exist and should be read first:** Lee/Steel 2025 fit a per-reactor **offset + scaling factor** against a dilution series; Stacey/Steel 2026 adapt **FPCountR** to a per-reactor linear a.u.→molar conversion; Díaz-Iza 2025 give **MEFL·particle⁻¹** units with public code. Note Sambruna's caveat that a per-device *scalar* is insufficient — the correction is concentration-dependent.

## P8 — Scheduled dosing / media-composition programs (literature-driven, 2026-07-18)

From the usage literature review (`docs/chibio-usage-literature-review.md`). **A real capability gap: two independent groups worked around the lack of programmed dosing manually.** Joshi et al. changed inducer setpoints by *swapping the media reservoir by hand* every 12 h; Wenk et al. drove a 150-day adaptive-evolution run with a *manually scheduled* medium-composition ramp (glycine down, formate up) — the turbidostat only held OD constant, the selection pressure came entirely from the media schedule. Today this fork offers a fixed OD/chemostat setpoint and per-user `CustomProgram`s, but no first-class notion of a timed recipe.

- [ ] **First-class staged media recipes + inducer/pressure ramps** in the turbidostat/pump UI: a schedule of (time or generation → target composition / pump action) that the control loop follows, beyond a single fixed setpoint. Would have directly replaced the manual reservoir swaps (Joshi) and the months-long ramp (Wenk). Pairs with the "dataset self-describes over time" item above — a scheduled change should log itself. Larger change; scope before building.

> Further literature-driven directions (optogenetic duty-cycle/pulse-train + dark-on programs; ReacSight-style external POST hooks + a declarative condition→action event layer + exhaustive per-actuation logging) are captured in the "Synthesis — directions ranked" section of `docs/chibio-usage-literature-review.md`. Not promoted to tracked items yet — lower priority than the two above.
