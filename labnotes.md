# Lab notes — Chi.Bio rig

Running record of every experiment and hardware test on this rig. Newest session at the
bottom. **All times are local (Europe/Rome, CEST = UTC+2)** and, unless marked `~`, are exact
values taken from server logs, CSV timestamps or metadata sidecars rather than recollection.

- `~` = approximate, inferred from surrounding log lines.
- **⬜ = not known to the software; needs filling in by hand.** Collected in
  [§ To fill in](#to-fill-in) at the end.
- Times recorded by the instrument are marked *(log)*; times done at the bench are *(bench)*.

---

## Rig configuration (persistent)

| | |
|---|---|
| Controller | BeagleBone Black, Debian 10.5, reached as `ssh ChiBio` → `root@10.39.161.52` (eth0) |
| Reactors fitted | **5** — M0–M4. M5–M7 are addressable in software, absent in hardware. |
| LED board version | **V2** on all five (auto-detected at every boot; FP3 uses the LEDE→LEDH remap) |
| Device IDs | M0 `6349460516117957796` · M1 `2048860525117957796` · M2 `10752604…` · M3 `17416603…` · M4 `29710602…` |
| OD source | `LASER650`, gain index 1 (calibration-locked, never auto-ranged) |
| OD calibration | `LASERa = 0.226`, `LASERb = 1.833` — shared by all eight slots from one template |
| OD formula | `OD = LASERb·log₁₀(OD0.target/raw) + LASERa·log₁₀(OD0.target/raw)²` |
| **Chi.Bio ↔ cuvette scale** | **2.81 ± 0.22 (CV 7.7%)**, measured 2026-08-12 on M0/M1/M4 at one density — see [Run 0 § outcome](#outcome). Provisional: a 6–8 point dilution series is still needed. |
| Spectrophotometer | ⬜ make/model, wavelength, cuvette pathlength |
| Vials | ⬜ type/supplier · 20 mL working volume · vented with 0.22 µm syringe filters (⬜ make) |
| Stir bars | ⬜ size/type |

**Standing gotcha:** the OD blank (`OD0.target`) lives in RAM only. Any server or worker
restart resets it to the stale 65000 default, which reads as a bogus OD ≈ 1.2–1.5. Re-blank, or
restore the previous value with `POST /CalibrateOD/OD0/<M>/<raw>/0`.

---

## 2026-07-14 — first hardware run of the refactored fork

*(log)* First successful boot of the `app.py` + `chibio_*.py` refactor on the device: M0/M1
initialised, LED V2 detected, watchdog up. Token/cookie auth verified end-to-end. I²C layer then
migrated off `Adafruit_GPIO` to `smbus2` and verified equivalent with `device_selftest.py`
before/after (readings matched within sensor drift).

No culture. Hardware/software verification only.

---

## 2026-07-17 → 07-18 — weekend batch run (GFP / YFP)

**Purpose:** first real culture run on the refactored fork; exercise OD + FP logging over a long
batch.

### Setup

| | |
|---|---|
| Reactors | **M0 = GFP**, **M1 = YFP**. M2–M4 not cabled at this time. |
| Strain | MG1655 (K-12) ancestral, fluorophore constitutively expressed from a **single chromosomal copy** (dim by design) |
| Exact strain IDs | ⬜ (TB204 sfGFP / TB201 mYFP?) |
| Medium | M9 salts + 0.2% glucose (minimal, glucose-limited, low autofluorescence) |
| Volume | ~1 mL inoculum into 24 mL → **25 mL** working volume |
| Inoculum | ~OD 0.45 stock (⬜ measured or assumed? ⬜ washed?) |
| Overnight prep | ⬜ start time, medium, temperature, shaking |
| Mode | Batch — no pumps, no reservoir |
| Thermostat | 37 °C, stir on, ~60 s cycle |
| Inoculation time (bench) | ⬜ |

### Timeline

| Time | Event |
|---|---|
| 2026-07-17 18:51:09 *(log)* | **M0 experiment started** |
| 2026-07-17 18:51:12 *(log)* | **M1 experiment started** |
| 2026-07-17 ~18:59 *(log)* | **Blanks applied at t = 0.13 h** — M0 `OD0.target = 15438.4`, M1 `= 15297.0` (zero-at-inoculation) |
| 2026-07-17 ~22:07 → 2026-07-18 ~00:13 *(log)* | FP1 active on M0, FP2 active on M1 (t = 3.3–5.4 h), then disabled |
| 2026-07-18 ~00:15 *(log)* | **Both reactors moved to FP3** for the rest of the run (t = 5.4–16.9 h) — a fresh slot, to escape contaminated FP history |
| 2026-07-18 ~11:45 *(log)* | Run ends, t = **16.90 h**, 1014 cycles per reactor |
| 2026-07-18 ⬜ *(bench)* | Experiment stopped, server restarted (RAM blanks lost) |
| 2026-07-18 13:02 | Data archived to `~/chibio-weekend-data/` |

### Results

| | M0 (GFP) | M1 (YFP) |
|---|---:|---:|
| rows | 1014 | 1014 |
| OD at t=0 (pre-blank, bogus) | 1.226 | 1.248 |
| OD max | 1.688 | 1.399 |
| OD final | 1.526 | 1.280 |

**Key finding — FP CLEAR-channel saturation.** At plateau the ratiometric readout ran at/near
the saturation ceiling: **M0 FP3 base exceeded 60000 in 277 / 1012 cycles (27%)** and fully
saturated (≥65000) in 6 cycles; M1 milder (52 cycles >60k, none full). No `valid=0` reads, so
the threat was *unflagged* saturation rather than dropped reads. This directly motivated the
near-saturation guard (`_FP_BASE_NEAR_SATURATION = 60000`).

Cuvette cross-check: ⬜ none taken.

---

## 2026-08-11 (daytime) — simulation mode, no reactors attached

*(log)* No hardware connected. `CHIBIO_SIM=1` built and verified; commits `73ec675`, `8b61879`
promoted to the device. **No `device_selftest.py` behind these commits** — the real I²C paths
could not be exercised with no reactors present.

---

## 2026-08-11 (evening) — all five reactors connected; hardware verification

Reactors M0–M4 cabled and powered for the first time. Device rebooted ~18:49.

| Time *(log)* | Event | Result |
|---|---|---|
| 18:52:33 | Server started, real mode (first boot with 5 reactors) | boots clean |
| ~18:53 | Presence scan | **M0–M4 present, M5–M7 absent, LED V2 on all five** |
| ~18:55 | `device_selftest.py fivereactors-2026-08-11` | **20 passed / 0 failed** — first ever 5-reactor verification |
| ~19:10 | Excitation-LED sweep (quick EEM, all five) | all six V2 LEDs respond on all five; zero invalid reads |
| ~19:25 | Stir PWM test, 0.6 for 45 s, dry | all five respond |
| ~19:30 | Heater open-loop test, 0.3 duty 4 min, dry, cutoff armed at 40 °C | all five heaters deliver power; **closed loop not testable dry** (Thermostat regulates on the IR sensor, which needs liquid) |
| ~19:35 | OD read-noise, empty static tubes | CV **0.12–0.14%** on raw transmission |

**Incident (method, not hardware):** firing `/MeasureOD/` at 1 s intervals produced `raw = 0`
with `valid = 1` on three of five reads. The route is fire-and-forget and settles in ~1.6 s;
overlapping threads switch `LASER650` off mid-read. **Reads must be spaced ≥5 s.** Runbook §7.1
updated.

### Bench prep (2026-08-11 evening)

| | |
|---|---|
| Medium | M9 salts + 0.2% glucose, ⬜ volume made, ⬜ time made, ⬜ autoclave time |
| Overnight culture | MG1655 WT, in M9 + 0.2% glucose. ⬜ start time, ⬜ temperature, ⬜ shaking speed, ⬜ volume |
| Overnight density | **not measured**; assumed OD 0.7–0.8 (typical for this medium) |
| Inoculum washed? | **No** — same medium, so no medium shift and minimal lag. Spent-medium fluorophores carried over at 2.5% v/v. |
| Per vial | 20 mL medium + **500 µL** inoculum (1:41) → implied start **OD ≈ 0.019 cuvette** |
| Sterile control | **M2** — 20 mL medium, no cells, labelled `M2 CTRL` |
| Vials | ethanol-wiped with lint-free paper before loading |
| Vents | 0.22 µm syringe filter on all five |
| **Inoculation time (bench)** | ⬜ |
| **Vials loaded into reactors (bench)** | ⬜ (before 19:45) |

### Reactor↔software mapping verified

*(log, ~19:56–20:05)* Confirmed by lighting reactors in distinguishable colours and reading the
physical labels: **M0 = blue (LEDB 457), M1 = green (LEDD 523), M2 = CTRL (dark, confirmed
separately with LEDF), M3 = red (LEDF 623), M4 = dark by elimination.** Physical labels match
software addressing one-to-one.

---

## 2026-08-11 → 08-12 — **RUN 0**: matched-control shakedown, WT in all four

**Purpose (per `docs/fluorescence-control-runbook.md`):** WT in every inoculated reactor plus a
sterile blank, to measure the reactor-to-reactor offset that Run 1's matched-control subtraction
depends on.

**Layout:** M0 WT · M1 WT · **M2 STERILE** · M3 WT · M4 WT.

### Timeline

| Time | Event |
|---|---|
| ⬜ *(bench)* | Inoculation (500 µL per vial into M0, M1, M3, M4; M2 none) |
| ~19:45 *(log)* | Thermostat 37 °C + stir 0.6 ON, all five. IR 25.2–26.2 °C |
| 19:51–19:52 *(log)* | Three large single-sample IR excursions — **caused by tube reseating at the bench**, not sensor faults |
| ⬜ *(bench)* | Tubes reseated to improve holder contact |
| 19:55:51 *(log)* | All five within 36.2–36.8 °C |
| 20:09:32–20:09:41 *(log)* | ⚠ First experiment start — **this run died, see below** |
| **20:12:57** *(log)* | ⚠ **`[CRITICAL] WORKER TIMEOUT (pid 1258)`** — gunicorn's default 30 s timeout killed the worker, wiping all RAM state 3 min into the run |
| 20:16:33 *(log)* | Server restarted with `--timeout 300 --graceful-timeout 60` (fix committed to `cb.sh`) |
| 20:18:48 *(log)* | Device-side supervisor v1 started |
| **20:18:59 / 20:19:01 / 20:19:03 / 20:19:06 / 20:19:08** *(log)* | ✅ **RUN 0 STARTS** — M0 / M1 / M2 / M3 / M4 |
| 20:22:39–20:22:47 *(log)* | **Blanks applied**, from the running experiment's own stir-off 3× median reads (in situ, at temperature, stir stopped — the manual's Troubleshooting procedure) |
| 20:22:50–20:28:38 *(log)* | **t0 EEM scan**, all five (near-sterile: culture ~2 doublings below the OD floor) |
| 22:05 / 22:11 / 22:19 *(log)* | ⚠ Three ladder rounds fired spuriously (see *Incidents*), real OD 0.13–0.28 |
| 22:22:17 *(log)* | ⚠ **M3's experiment thread died** during its own ladder scan |
| **22:48:27–22:49:04** *(log)* | **FP gain reduced 512× → 32× (index 10 → 6) on all five** — logged to the events sidecar |
| ~22:56 *(log)* | M3 recovered without a server restart (`/Experiment/0/M3` → `/Experiment/1/M3` + explicit stir re-assert) |
| 23:29:39 *(log)* | Ladder scan at trusted-median OD 0.705 |
| 23:41:07–23:41:31 *(log)* | M3 stalled again at cycle 149; **auto-recovered in 24 s** |
| 23:58:27 *(log)* | Ladder scan at trusted-median OD 1.007 |
| 00:35:46 / 00:50:20 / 02:07:49 / 02:09:28 / 02:36:08 / 05:10:14 *(log)* | Six automatic FP gain step-downs (M4 FP1→x5→x4, M1 FP1→x5→x4, M1 FP2→x5, M0 FP1→x5) |
| **09:30:52** *(log)* | ⚠ **Second `WORKER TIMEOUT` (pid 2142)** despite `--timeout 300`. **Cause not yet established.** Ends the primary dataset at **13.2 h**. |
| 09:36:00–09:38:02 *(log)* | Supervisor's stall-recovery restarted all five into **new, unblanked CSVs** (a bug — see *Incidents*) |
| ~10:27 *(log)* | Original blanks restored by hand |
| **10:29:29** *(log)* | **Final paired snapshot** taken (the reference for the cuvette comparison) |
| ~10:31 *(log)* | All experiments, heaters, stirrers, thermostats stopped |
| ⬜ *(bench)* | Tubes removed from reactors |
| ⬜ *(bench)* | Cuvette readings taken |

### Blanks applied (`OD0.target`, raw counts)

| M0 | M1 | M2 | M3 | M4 |
|---:|---:|---:|---:|---:|
| 14744.0 | 15536.3 | 11650.7 | 15764.3 | 13118.0 |

### FP configuration (identical on all five)

| Slot | Excite | Emit1 / Emit2 | Intended for |
|---|---|---|---|
| FP1 | LEDB 457 | nm510 / nm550 | sfGFP |
| FP2 | LEDD 523 | nm550 / nm583 | mYFP |
| FP3 | LEDH 600 | nm620 / nm670 | mCherry |

Gain **x10 (512×) from 20:19 until 22:49**, then **x6 (32×)**, then stepped down further per the
timeline. The logged emit values are emit/base **ratios**, which are gain-invariant, so the
change does not break comparability. Raw emission is recoverable as `emit_raw = emit_ratio ×
FP*_base`, with `FP*_gain_used` logged per row.

### Data products

| File | Contents |
|---|---|
| `2026-08-11 20_18_59_M0_data.csv` (+ M1/M2/M3/M4) | **Primary dataset** — 13.2 h, ~650 rows each, blanked |
| `*_meta.json` | Per-run metadata sidecars |
| `*_events.json` | Blank + FP-config changes, timestamped |
| `eem_*.json` (33 files) | EEM captures spanning OD 0.01 → 1.04 |
| `final_snapshot_preremoval.json` | The 10:29:29 paired snapshot |
| `2026-08-12 09_36_*_data.csv` | Secondary ~1 h stub at plateau, **unblanked** — low value |
| `2026-08-11 20_09_*_data.csv` | 3-cycle stubs from the run that died at 20:12:57 — **discard** |

**Archived 2026-08-12 to `~/chibio-run0-2026-08-11/`** (2.7 MB). All five primary CSVs
**md5-verified against the device**. Contents: 5 primary CSVs (297–323 kB each) · 5 meta
sidecars · 10 events files (5 primary, 5 from the secondary stub) · 33 EEM captures ·
`final_snapshot_preremoval.json` · `logs/` (server + all supervisor logs) · `secondary/` (the
unblanked 09:36 stub run).

⚠ **The EEM rounds are not all complete** — counts by tag: t0 = 5, OD0.2 = 7, OD0.4 = 5,
OD0.6 = 5, **postgain = 1**, OD0.7 = 5, OD1.0 = 5. The `postgain` round has only M0 because the
supervisor was stopped mid-round to recover M3, and `OD0.2` has 7 because a second round began
before the trigger was fixed. **The tag is not the density** — always use the actual OD in the
filename and in each payload's `od_before`.

### Outcome

**Growth** (log-linear fit, first 3 h, offset = 0.049 Chi.Bio units from the measured scale factor):

| | µ (/h) | t_d | R² | OD max | plateau at |
|---|---:|---:|---:|---:|---:|
| M4 | 0.835 | 49.8 min | 0.963 | 2.411 | 10.9 h |
| M1 | 0.779 | 53.4 min | 0.957 | 2.943 | 9.9 h |
| M3 | 0.660 | 63.0 min | 0.684 | 1.276 | 6.8 h |
| M0 | 0.404 | 102.9 min | 0.738 | 1.523 | 10.7 h |
| M2 *(sterile)* | 0.077 | — | 0.089 | 0.047 | — |

**Cuvette cross-check, 2026-08-12 ⬜ *(bench)*.** Spectrophotometer zeroed on ⬜ (not on M2 —
M2 itself reads 0.054). Sterile M9 + 0.2% glucose from **M2 was used as the diluent**, so the
medium background stays 0.054 in the diluted samples too.

| | Chi.Bio (10:29:29) | cuvette undiluted | cuvette 1:5 (×5) | used | − medium | **ratio** |
|---|---:|---:|---:|---:|---:|---:|
| M0 | 1.558 | 0.651 | — | 0.651 | 0.597 | **2.610** |
| M1 | 2.859 | ~~1.138~~ | 0.260 → 1.300 | 1.300 | 1.030 | **2.776** |
| M2 | 0.026 | 0.054 | — | — | — | — |
| M3 | 1.079 | 0.628 | — | 0.628 | 0.574 | *1.880* |
| M4 | 2.323 | ~~0.983~~ | 0.207 → 1.035 | 1.035 | 0.765 | **3.037** |

**Undiluted M1 and M4 are discarded** — both sat above the linear range and read low by 14% and
5% respectively. That compression scales with OD exactly as expected, which is the internal
check that the 1:5 readings are the sound ones. M0 (0.651) and M3 (0.628) were in range and are
used as read.

Convention note: Chi.Bio was blanked *at inoculation*, so its zero already contains the
inoculum's ~0.019 cuvette OD of cells, whereas the cuvette figures above are referenced to
sterile medium. Subtracting the inoculum from the cuvette side to match would give a scale of
2.88 (CV 7.4%) — a 2% effect that changes no conclusion. **2.81 is quoted against the
sterile-medium convention.**

**Findings**

1. **Chi.Bio ↔ cuvette scale = 2.81 ± 0.22, CV 7.7%** across M0/M1/M4 (2.610 / 2.776 / 3.037).
   **Provisional and weaker than it first appeared.** An initial pass using the *undiluted*
   M1/M4 readings gave CV 2.8%, but that was an artifact: both were compressed by
   spectrophotometer nonlinearity (14% and 5%), and the two errors happened to pull their
   ratios toward M0's. With the 1:5 values the honest spread is ~7.7%. This is consistent with
   the `CLAUDE.md` claim that reactor identity does not change the OD math, but it does **not**
   settle it — 7.7% at a single density is equally consistent with a few percent of real
   per-reactor difference. The deciding experiment is still the **6–8 point dilution series on
   two reactors** in `docs/audit-2026-08-11-findings-and-actions.md` §7.1. What this does give
   is a usable conversion anchored at the top of the range.
2. **M0's low density is real biology, not optics.** Its scale ratio (2.610) is the closest of
   any reactor to M1's (2.637), so its optics are sound; it genuinely grew to 57% of M1's
   density at half the rate, with the highest replicate spread all run.
3. **Reactor-to-reactor variation is dominated by mixing/aeration, not optics.** The µ ordering
   (M4 > M1 > M3 > M0) tracks observed mixing quality — M1 visibly bubbly and vigorous, M0
   persistently high-spread.
4. **M3 is the one optical outlier** (ratio 1.880 = 67% of the others; outlier under every
   background assumption tried, so not an artifact of how the medium blank was handled). It sat unstirred ~30 min
   and stalled twice, and its OD peaked at 6.8 h then declined — the settling signature. Treat
   M3's absolute ODs as suspect and its µ as a lower bound.
5. **Sterile drift floor:** M2 moved from −0.015 to +0.044 over 13 h. Not exponential, so not
   contamination. That ~0.06 is the instrument + vial drift over a full run.
6. **The FP gain change fixed saturation completely** — 0% NaN on all five reactors and all
   three slots after 22:53, against 24–57% losses before it.

### Incidents (all written up in `TODO.md`)

1. **Two gunicorn worker timeouts** (20:12:57, 09:30:52). Each wipes all RAM state — blanks,
   FP config, cycle counts — while the port stays open and nothing looks wrong from outside.
   The first was the default 30 s timeout (fixed). **The second, at `--timeout 300`, is
   unexplained.**
2. **A `FluorescenceScan` can kill the scanned reactor's experiment thread** (M3, 22:22:17).
   Worse than the lost rows: the thread died just after turning stir OFF, so M3 sat unstirred
   ~30 min, and `OD.current` froze at a plausible, stable, **unflagged** value (1.681).
3. **A `FluorescenceScan` corrupts the scanned reactor's concurrent OD row** — `raw = 0`,
   `valid = 1`. Analysis filter: `od_transmission_raw != 0`.
4. **Supervisor stall-recovery made incident 1 worse** — it cannot distinguish "one thread died"
   from "the whole worker was wiped", so at 09:36 it restarted all five into unblanked CSVs
   instead of stopping and alerting.
5. **Two concurrent scripts calling `/changeDevice/` corrupted a blanking pass** (20:0x). One
   supervisor process only.

---

## 2026-08-12 — M4 reactor unit failed; rig now four reactors

**Symptom.** From 11:22 the server could not boot: `Multiplexer comms failed on M4` → `Failed to
recover multiplexer on M4` → worker `exited with code 4` → `App failed to load`. Exit 4 is the
watchdog deliberately killing the process rather than letting a wedged I²C bus drive actuators —
**working as designed, not a software bug.** Each boot ran ~15–50 s (M0–M3 initialising silently
and successfully) before M4 wedged the shared bus.

**Trigger.** Physical handling of vials and reactors during the stir investigation. No fault had
appeared during the 13 h run.

**Diagnosis** — the server's refusal to boot used as a binary instrument, one variable per test:

| Configuration | Errors | Conclusion |
|---|---|---|
| M4 in its own port | 40 × "on M4" | — |
| M4 connector reseated firmly | 40 × "on M4" | not seating |
| M4 on the pump cable | 40 × "on M4" | **not the cable** |
| Full power-down 10 s, reboot | 40 × "on M4" | not a latch-up |
| **M4 unplugged** | **0 — clean boot** | fault confined to M4's branch |
| **M4 reactor on controller port T7** | **40 × "on M7"** | **fault follows the reactor** |

**Conclusion: the M4 reactor unit is faulty.** Cable, connector seating, controller channel and
power are each excluded by a clean negative test. Ports T4 and T7 both work.

**Prior signals on M4, all before the failure:**
- 2026-08-11 22:22:28 — `Failed transmission test on PWM ... on device M4`
- repeated `Spectrometer measurement was saturated on device M4` warnings through the run
- highest FP NaN rate before the gain change (49% of FP1 rows)

**State after:** M0–M3 verified healthy — presence scan clean, `device_selftest.py
post-M4-removal` **16 passed / 0 failed**. The suspect original cable is now on **pump 4** and is
labelled; do not reuse it on a reactor without testing.

**Consequence for Run 1:** the runbook is scoped for five slots and does not fit in four. The
three non-negotiables (WT at n=2, plus the sterile blank) take three slots, leaving one FP arm
instead of two — so either the WT replicate or one of mCherry/sfGFP has to go. **Decision
pending.**

⬜ Time M4 was unplugged and retired · ⬜ what to do about a replacement

---

## 2026-08-13 (00:30 → 01:35) — the Run 0 vials as a matched-control experiment

**No new culture was set up.** The Run 0 vials were still in M0–M3: WT in M0, M1, M3 and the
sterile-medium blank in M2, ~29 h after inoculation, heater off and stirrer off since
2026-08-12. Every vial in the rig was therefore **non-fluorescent**, which makes the whole rig a
known-answer test for the fluorescence assist: the correct answer for each of the four reactors
is "no fluorophore".

Nothing was inoculated, blanked, or reconfigured. Actuation was limited to the stirrer (to
homogenise before reading) and the excitation LEDs the scan drives and switches off itself.
Scripts: `probe_cultures.py`, `probe_repeat.py`, `probe_reference.py` (all in the repo).

### State at 00:30 *(log)*

M0–M3 present, M4 absent (retired 2026-08-12). Experiment off, all outputs off, `OD0.target`
still the stale 65000 default, so **every absolute OD below is uncalibrated** — raw transmitted
counts are quoted instead.

| | M0 | M1 | M2 (sterile) | M3 |
|---|---|---|---|---|
| OD raw, settled (counts) | 2107 | 799 | 10293 | 2165 |
| Internal air (°C) | 26.19 | 29.94 | 27.25 | 26.00 |
| IR / media (°C) | 26.47 | 28.51 | 26.15 | 26.27 |
| External air (°C) | 36.25 | 36.25 | 36.25 | 36.25 |

⬜ **The external-air thermometer read exactly 36.25 °C on all four reactors**, with the heaters
off and the cultures at ~26 °C. Four independent sensors agreeing to the digit on a value ~10 °C
above everything else is not a plausible measurement. Treat `external_air_temp` as suspect until
someone checks it at the bench; it is not used by the thermostat (which runs off the IR/media
sensor), so no control loop depends on it.

⬜ **The sterile blank has lost 11.7 % of its transmission**: M2 read 11651 counts when it was
blanked at Run 0 start and 10293 now. It is the only reactor whose contents should not change.
Worth a look before the tube is reused — contamination and condensation both fit.

### Sedimentation is visible inside one measurement window

Each reactor was stirred 2 min, the stirrer stopped, and three OD reads taken 8 s apart (the
optical state `runExperiment` measures in):

| | read 1 | read 2 | read 3 | drift |
|---|---|---|---|---|
| M0 | 2263 | 2156 | 2077 | −8.2 % |
| M3 | 2278 | 2137 | 2047 | −10.1 % |
| M1 | 775 | 753 | 734 | −5.3 % |
| M2 (sterile) | 10312 | 10337 | 10288 | −0.2 % |

Transmission *rises* monotonically across the replicate series in every reactor holding cells and
is flat in the one that does not, i.e. cells are settling out of the beam over the ~16 s the three
replicates take. The sterile tube bounds the read noise at ±0.2 %. This is a stationary-phase,
unheated culture, so it is an upper bound on what a stirred exponential culture would do — but it
means `od_spread` mixes two things, a genuine mixing signal and a monotonic sedimentation ramp,
and the 3× median lands nearer the *later* (more settled) reads than the first.

### Every reactor, including the sterile blank, was told it was fluorescent

Quick fluorescence scans, LED power 0.5, stir off + 5 s settle:

| reactor | contents | recommendation | reported "signal" |
|---|---|---|---|
| M2 | **sterile medium** | LEDI (550) → nm583 / nm620 | 37.7 |
| M0 | WT | LEDI (550) → nm583 / nm620 | 269.6 |
| M3 | WT | LEDI (550) → nm583 / nm620 | 275.9 |
| M1 | WT (densest) | LEDI (550) → nm583 / nm620 | 516.2 |

All four are false positives, and **the reported signal is ordered by turbidity** — the sterile
tube gets the same cell recommended at 1/7 the magnitude. This confirms the 2026-07-17/18
finding (identical `ex550→nm583/620` for GFP and YFP) and settles what it was reading: not the
fluorophore, and not only cellular autofluorescence either, since a tube with no cells in it
produces the same pick.

**Scan-to-scan repeatability**, 3 repeats per reactor over 9 min with a re-homogenise before each:

| reactor | signal r1 / r2 / r3 | per-cell CV across the EEM |
|---|---|---|
| M2 | 37.7 / 37.6 / 37.6 | median 0.07 %, worst 0.39 % |
| M0 | 274.9 / 275.2 / 276.3 | median 0.44 %, worst 4.6 % |
| M3 | 284.1 / 283.5 / 282.2 | median 0.38 %, worst 2.3 % |
| M1 | 517.6 / 520.0 / 523.2 | median 0.40 %, worst 1.3 % |

The instrument is repeatable to ~0.4 %. Whatever separates two reactors is therefore not read
noise.

### Subtracting a matched non-fluorescent reactor

Fitting a single scale factor to a reference EEM and subtracting it (median of the per-cell
ratios, so one genuinely fluorescent cell cannot drag the fit):

| sample − scaled reference | fitted scale | median \|residual\|/signal | 90th pct |
|---|---|---|---|
| M3 − M0 (WT vs WT, same density) | 1.03 | **6.3 %** | 18 % |
| M0 − M3 (reversed) | 0.99 | 8.2 % | 21 % |
| M1 − M0 (WT vs WT, 1.8× denser) | 2.02 | 14.4 % | 40 % |
| M0 − M2 (culture vs **sterile**) | 9.12 | 22.6 % | 65 % |
| M1 − M2 (culture vs **sterile**) | 17.14 | 19.7 % | 50 % |

Three results worth carrying forward:

1. **A matched WT culture removes ~92–94 % of the background**, and the leftover 6–8 % is ~15×
   the read noise, so it is real reactor-to-reactor optical difference, not measurement error.
   That 6–8 % is the floor any fluorophore has to beat when the control lives in a *different* vial.
2. **A sterile tube is not a substitute for a matched culture** (20–23 % residual). Medium
   scatters differently from cells. The sterile blank earns its slot for the OD/instrument floor,
   not as the fluorescence control.
3. **Density matters**: matching to within ~1.05× halves the floor versus a 1.8× mismatch.
   Same-reactor referencing (scan before induction, scan after) should do far better again, since
   repeatability is 0.4 %.

### Reference subtraction, driven on the live cultures

Implemented (see the code section below) and then run against the four real vials through the
real route. Every case is a true negative by construction:

| case | setup | result |
|---|---|---|
| 1 | M3 scanned with no reference | LEDI→nm583, signal 281.1, labelled **unverified** |
| 2 | M0 referenced against M3 (scale 0.97) | **no recommendation** — the correct answer |
| 3 | M1 referenced against sterile M2 (scale 16.5) | **no recommendation**, despite the 17× mismatch |
| 4 | reference cleared from M0 | back to the unverified LEDI→nm583, signal 276.6 |
| 5 | reference requested from a device with no scan | refused, HTTP 409 |

### Retrospective analysis of the archived runs

**Run 0 (2026-08-11), from the CSVs and the events sidecars.**

- **Per-reactor blanks span 1.35×** on the same medium at the same laser power: M2 11651,
  M4 13118, M0 14744, M1 15536, M3 15764 counts (CV 12.3 %). This is the per-reactor optical
  difference that blanking absorbs, and it is not small.
- **The FP background in a WT culture is almost entirely instrument, not biology.** The
  sterile M2's emit/base ratios sit inside the spread of the four WT cultures' — FP3 nm620:
  sterile 0.518, WT 0.489–0.556. Ratios *fall* slightly with OD in every channel. Because both
  the emission and the CLEAR base scale with scatter, the ratio is largely scatter-invariant and
  what it reports is the spectral shape of the excitation leak.
- **σ_device across the four WT reactors at matched OD**: CV 5.1 % (FP3 nm620) to 23.9 %
  (FP2 nm583), with M1 the high outlier in every channel. Cross-device fluorescence comparison
  without per-reactor calibration is not supportable at this spread.
- **Cross-reactor subtraction of the FP-slot ratios** (M1 as control for M0/M3/M4) leaves 8–53 %
  of the raw ratio depending on channel — much worse than the EEM-level subtraction above,
  because a single FP slot has no scatter cells to fit a scale on.
- **The emit/base ratio is not perfectly gain-invariant.** Across the mid-run x10→x6 change the
  ratio moved −1.5 % (FP3), −2.4 % (FP1) and −7.8 % (FP2), against an OD drift that accounts for
  only ~0.2 %. The claim that a mid-run gain change is safe for comparability holds to within
  roughly ±8 %, not exactly. ⬜ Worth a deliberate gain ladder on one reactor to pin down.

**July weekend run (2026-07-17/18) — mostly unusable for cross-run FP comparison.**

- Excitation LEDs ran at power **0.5**, against **1.0** in Run 0. Recorded in the CSV
  (`LED_457nm_setpoint` etc.), so it is recoverable, but it is a confounder for any raw-count
  comparison between the two runs.
- **It predates the events log**, and the metadata sidecar only captures the configuration at
  *start* (all three FP slots `on: 0`). The slots were switched on mid-run — FP1 on M0 for 126
  rows, FP2 on M1 for 127, FP3 on both for ~690 — so which bands produced which numbers is not
  recoverable from the archive. This is exactly the gap `logEvent` was added to close, and it
  closed it: Run 0's sidecars record every FP config change with an `exp_time`.
- Note for anyone reading these CSVs: **an inactive FP slot logs `0`, not `NaN`**, so a
  zero in an FP column means "slot off", not "no signal". Filter zeros before taking medians.

### Code changed today

- **Matched non-fluorescent reference subtraction** in the fluorescence assist
  (`chibio_fluorescence.py`, route `/SetFluorescenceReference/<M>/<source>`). A recommendation is
  now made on the residual after subtracting a scaled reference EEM, and carries
  `confidence: referenced|unreferenced`. Without a reference the old pick is preserved but is
  labelled unverified and says why. Thresholds come from the measurements above.
- The UI shows the verdict, the reference controls, and a **counts/residual toggle** on the
  heatmap. Verified on the device in both themes.
- **Bug found while verifying (pre-existing):** switching the UI to a reactor with no scan left
  the *previous* reactor's EEM and recommendation on screen under the new reactor's name — one
  vial's settings offered for another's. The panel now clears and says which reactor has no scan.

Off-device suite 13/13; `device_selftest.py` 16/16 on staging and again on production.

---

## 2026-08-13 (10:20 → 11:05) — timed dosing schedules, built and driven on a live reactor

Software session; no culture work. The Run 0 vials were still in M0-M3 (WT in M0/M1/M3, sterile
medium in M2) and were used only as a live target to drive code against. **Nothing was pumped
into any vial** — the schedule test drove LEDB at 0.3 power and the (inactive) thermostat
setpoint, which exercises the whole path including real I2C without moving liquid.

### What was tested on the device

A schedule was set on M2, an experiment started (OD control off, so a cycle measures and logs but
does not pump), and the schedule run for ~3.5 min:

| | |
|---|---|
| Validation refusals | 4/4 returned HTTP 400 naming the offending stage — unknown channel, out-of-range target, negative hour, ramped stir |
| Scheduled LED step | on at the 18 s mark at target 0.300, off at 50 s, through real I2C |
| Ramped setpoint | 30.26 → 31.05 → 31.85 → 32.65 → 33.44 → 34.00, then held — linear, as specified |
| `schedule_stage` CSV column | present, 64 columns, read 1 then 4 across four cycles |
| Events sidecar | three `schedule_stage` transitions recorded |
| Outputs after | all off, experiment stopped, schedule stopped |

`device_selftest.py` **16/16** on staging and again on production. Off-device suite **15/15**.

Test artifacts (the short M2 and M0 runs) were moved to `/root/schedule-test-artifacts/` so they
do not sit among real data.

### Three things worth remembering

- **A template edit needs a gunicorn restart.** Jinja's auto-reload follows `app.debug`, which is
  off, so `rsync`ing `templates/` changes nothing until the worker restarts — while `static/`
  (JS/CSS) *does* update on a browser reload. That asymmetry cost a confused ten minutes reading
  a CSS rule as broken when it simply was not being served.
- **The `M == "0"` sentinel is easy to miss in a new module.** Every route accepts `0` for "the
  reactor the UI is showing", and the UI's own buttons post to `/SetSchedule/0`. The new module
  did not resolve it, so every button in the panel returned a bare 500 — and the device probe
  missed it entirely because it passed `M2` explicitly. **A probe that addresses reactors by name
  does not exercise the path the UI actually uses.**
- **Stir cannot be ramped, and that is a hardware fact, not a preference.** `SetOutput`'s Stir
  branch hard-starts the motor at full power for 1.5 s on any target change (INVARIANTS §6), so
  a ramped stir would kick the motor every tick for the whole ramp. Now refused at validation.

---

## To fill in

Please add these — the software has no way to know them.

**General / rig**
- [ ] Spectrophotometer make, model, wavelength, cuvette pathlength
- [ ] Vial type and supplier; stir bar size/type; vent filter make

**July 2026-07-17 run**
- [ ] Exact strain identities for "GFP" (M0) and "YFP" (M1)
- [ ] Overnight prep: start time, medium, temperature, shaking
- [ ] Whether the OD 0.45 inoculum was measured or assumed; whether it was washed
- [ ] Inoculation wall-clock time
- [ ] Time the run was stopped on 2026-07-18

**2026-08-13 probes**
- [ ] Why does `external_air_temp` read exactly 36.25 °C on all four reactors with the heaters off?
- [ ] Is the sterile M2 blank still sterile? Its transmission fell 11.7 % over ~29 h.
- [ ] Time the Run 0 vials are finally discarded

**August Run 0**
- [ ] Medium: volume made, time made, autoclave time; glucose filter-sterilised separately?
- [ ] Overnight culture: start time, temperature, shaking speed, volume
- [ ] **Inoculation wall-clock time** (when the 500 µL went into each vial)
- [ ] Time the vials were loaded into the reactors
- [ ] Time the tubes were reseated (~19:52 from the IR trace — confirm)
- [ ] Time the tubes were removed on 2026-08-12
- [ ] Time the cuvette readings were taken
- [ ] Anything observed at the bench not in the log (foam, colour, smell, condensation)
