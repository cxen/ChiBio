# Audit findings and actions — handoff, 2026-08-11

**Who this is for:** a later agent (or human) who will either **implement changes to this fork**
or **plan bench experiments on the rig**, and who was not present for the audit that produced it.

**What it is:** the actionable output of a completeness audit of the Chi.Bio usage literature,
run across eight parallel avenues on 2026-08-11. It is a *work order and a briefing*, not the
evidence. **The evidence is `docs/chibio-usage-literature-review.md` (revision 2)** — every claim
here is traceable to a numbered section there, and where a claim matters, the section is cited.

**How to trust it.** Three confidence tiers are used throughout and they mean different things:

| Tag | Meaning |
|---|---|
| **VERIFIED** | Checked directly against this fork's source or against a primary document during the audit. Act on it. |
| **SOURCED** | Stated by a primary source (paper, datasheet, vendor, or another lab's code) but not tested on this rig. Design against it; confirm on the device. |
| **INFERRED** | The audit's judgement from converging evidence. Reasonable, but argue with it before spending a week on it. |

Anything not tagged is orientation, not a claim.

---

## 0. Read these first — non-negotiable process

These are existing repo rules, restated because every item below trips at least one of them.

1. **Hardware-first.** `CHIBIO_MOCK_HW=1` is an import shim, not a development target;
   `CHIBIO_SIM=1` is a fake bus with a plausible culture behind it, not the rig. Which LED version
   is fitted and which reactors are present decide what the UI even renders. `ssh ChiBio`, run the
   server, `curl /getSysdata/`, and drive any off-device preview from a **real captured snapshot**.
   See `CLAUDE.md` → "What this is".
2. **Any UI change runs the fixed skill sequence** — device state → `/frontend-design` →
   `/better-colors` → `/better-typography` → `/better-ui` → `/emil-design-eng` →
   `/critical-code-reviewer`. Standing policy; does not need to be asked for. Several items below
   are UI-facing and are marked **[GUI]**.
3. **Deploy/verify loop:** rsync to `/root/chibio-staging`, boot, `device_selftest.py`, then
   promote to `/root/chibio`. Stop the server **only** via `cb-stop.sh`. See the
   `device-deployment` memory.
4. **Never `git push` before device testing** — this is a public fork.
5. **One supervisor process only.** `/getSysdata/` returns only the UI device, so two processes
   calling `changeDevice` read each other's reactor. See the `single-owner-device-scripts` memory.
6. **OD blanks live in RAM.** Re-blank after any restart, or the OD column silently changes
   meaning mid-dataset. See `od-blanking`.

---

## 1. Verified defects — fix these first

All four are **VERIFIED** in this fork's source during the audit. They are tracked in `TODO.md`
under "Found by the literature/code audit, 2026-08-11". None is fixed yet.

### 1.1 AS7341 saturation is undetectable at short integration times — and can misdetect a V2 board as V1

**Impact: highest of the four.** A misdetected LED version means the wrong excitation panel and no
FP3 LEDE→LEDH remap, on a board this rig actually has.

- **Where:** `chibio_optics.py:14` (`_ADC_SATURATED = 65535`), `:83`, `:176`; the failing caller is
  the LED V1/V2 auto-detection at `app.py:257–270`.
- **The fact (SOURCED, ams DS000504 Eq. 2):** full scale is `(ATIME+1)×(ASTEP+1)`, **capped** at
  65535 — it is not *always* 65535. `ASTEP` resets to 999 and this fork never writes it, so full
  scale is a function of the `ISteps` argument.
- **The bug (VERIFIED):** auto-detection calls `get_light(M,['nm583'],10,10)` — `ISteps=10` →
  full scale `(10+1)×(999+1) = 11,000`. Every saturation check tests against 65535, so a saturated
  read is invisible. If a bright board pins both `Baseline` and `NewLevel`, the test
  `NewLevel > Baseline*3+20` evaluates false and the code concludes "LED absent", falling through
  to `Version['LED'] = 1`.
- **Corroboration:** upstream noticed the symptom and never diagnosed it —
  `chibio_optics.py:84` carries the comment *"Not sure if this saturation check above actually
  works correctly…"*.
- **Fix:** compute the ceiling as `min(65535, (ISteps+1)*(ASTEP+1))` — or write `ASTEP` explicitly
  and keep the constant honest. Do not just raise `ISteps` in the detection path without
  re-validating the 3× threshold.
- **Test:** off-device, assert the computed ceiling for `ISteps` ∈ {10, 255}. On-device, confirm
  `Version['LED']` still reads 2 on all five reactors after the change (review §1.4).

### 1.2 The chip reports saturation in hardware and we have the read commented out

- **Where:** `chibio_optics.py:72` — `#Status2=int(I2CCom(M,'AS7341',1,8,0xA3,0x00,0))`.
- **Why it matters (SOURCED, DS000504 pp. 45–47):** `ASAT_ANALOG` fires **before** the digital
  counter fills. **No threshold on the returned number can ever see analog saturation** — including
  `_FP_BASE_NEAR_SATURATION`. That is exactly the regime a 90° scatter geometry with a bright LED
  at 512× gain operates in. `ASAT_DIGITAL` is integration-time-aware, so it is correct at any
  `ISteps`, unlike the hardcoded 65535.
- **Better still:** `ASTATUS` (0x94) returns the saturation flag **and the gain actually applied**,
  latched with the same integration — one extra byte, and the applied gain is what an EEM needs for
  correct normalisation.
- **Fix:** fold into the existing `valid` flag rather than replacing `_FP_BASE_NEAR_SATURATION`.
  Belt and braces: the count threshold catches the ratio going nonlinear, the hardware flag catches
  the front end pinning.
- **While you are there, two SOURCED accuracy notes worth a comment in `chibio_fluorescence.py`:**
  - `_gain_multiplier`'s nominal `0.5·2ⁿ` is wrong at the top: **512× delivers ≈7.75× the 64×
    response, not 8×** (±6% part-to-part). ~7% systematic error across the range an auto-ranging
    EEM spans.
  - **Band labels are ~5 nm below the ams typicals** (415/445/480/515/555/590/630/680 vs
    410/440/470/510/550/583/620/670), with `nm470`/`nm620` at the *edge* of tolerance. The
    Stokes-shift rule should carry **±10 nm**.

### 1.3 `PumpModulation` issues duplicate `setPWM` off-pairs

- **Where (VERIFIED):** `chibio_experiment.py:26–29` and `:59–62` — verbatim duplicate pairs.
- **Impact:** 4 redundant I²C transactions per pump per cycle, each acquiring the global `lock` and
  switching the mux. With 5 reactors × 4 pumps that is real pressure on precisely the resource
  whose contention produces "Failed to recover multiplexer" (review §3.1).
- **Fix:** delete the duplicates. Published upstream as `alje-lab@0d395e5`.

### 1.4 `PumpModulation` pump timing is biased and 10 ms-quantised

- **Where (VERIFIED):** `chibio_experiment.py:34` (`Time1=datetime.now()`), `:55`
  (`time.sleep(Ontime)`), `:65–67` (`round(...,2)`).
- **Impact:** `time.sleep` overshoots badly at short durations on this hardware, so **every
  dilution volume carries a systematic positive bias**, quantised to 10 ms. This is a quiet
  quantitative error in the turbidostat — i.e. in the dilution rate that growth-rate estimates are
  derived from. It is not cosmetic.
- **Fix (`alje-lab@5d7516e`, `59fdf0c`):** `time.perf_counter()`, `round(…,5)`, and a **spin-wait**
  for `Ontime < 0.5 s`; log the achieved on-time in ms so you can see whether duty cycles are what
  you asked for.
- **Sequencing note:** do 1.3 and 1.4 together; they touch adjacent lines.

---

## 2. The data-schema change that unblocks everything else

**This is the highest value-per-line change in the audit, and revision 1 of the review did not
have it at all.**

### 2.1 Log raw OD and raw FP emissions

- **The problem (VERIFIED against the code; SOURCED from Steel on the forum — *"the system doesn't
  record the RAW OD values … so you need to back-calculate these"*):** Chi.Bio computes the raw
  laser value and discards it, and stores FP as emit/base **ratios** only.
- **Two consequences, both already biting:**
  1. Combined with a **RAM-only blank**, a mid-run restart silently changes the meaning of the OD
     column with no way to recover the original. This is the `od-blanking` fragility made
     unrecoverable after the fact.
  2. **Matched non-fluorescent-control subtraction cannot be retro-fitted to data already
     collected** while only ratios are stored. Every source that recommends the technique needs
     raw emission counts.
- **What to add:** `od_raw` (from `sysData[M]['OD0']['raw']`) and `FP{1,2,3}_emit{1,2}_raw`,
  captured **before** the Clear-ratio division.
- **How:** this fork's documented 2–3 place edit — `initialise()` in `app.py` (create the `record`
  list), `csvData()` in `chibio_control_helpers.py` (one `data[...] =` line each, `DictWriter`
  keys by name so header and row cannot drift), and `downsample()` if it should be downsampled.
- **Prior art:** `zoltuz/ChiBio @ imperial_GBS` ships exactly these columns. `Janmorlock/ChiBio`
  re-multiplies `Emit1 × Base` inside its estimator to recover a pseudo-raw value — a tacit
  admission that the ratio is the wrong quantity to model.
- **Do this before the matched-control experiment runs**, or the run produces data that cannot
  answer the question it was designed for. See §4.3.

### 2.2 Record the optical configuration in the metadata sidecar

Cheap, and it makes a non-standard rig self-describing: OD source/wavelength (`LASER650` today),
`LASERa`/`LASERb`, the blank value **and its timestamp**, LED version (V1/V2), and per-LED
intensity units.

Two live scenarios need it (**SOURCED**): the cyanobacteria community is being told by Steel to
**desolder the 650 nm diode and fit a ~700–800 nm one** (after which the CSV would silently still
claim OD650), and an optogenetics group had to cross-calibrate Chi.Bio's arbitrary LED units
against µmol m⁻² s⁻¹ to make their light dose reportable (review §2.5, §6).

---

## 3. Scheduled dosing — the most corroborated gap

**Promoted above fluorescence in revision 2.** Evidence (review §7 item 5): six papers — **four of
them from Steel's own lab** — six independent forum threads all answered with *"add a conditional
statement in the main loop which turns the pumps on every 12*60=720 cycles"*, and an outside
benchmark (ModuloStat, ACS Omega 2026) that scores Chi.Bio as **dilution-rate feedback only**,
where seven peer platforms also do chemical composition.

### 3.1 The key reframing

**The selective pressure is almost never the dilution loop.** Across the corpus it is:

| Actuator | Example |
|---|---|
| Medium composition | Wenk (glycine ↓ / formate ↑ over 150 d), Klass (malonate-limited) |
| **Temperature** | Deng (37 → 27 °C over 2 weeks), Lee/Steel (composition control) |
| **UV** | Corrao/Steel (PI on growth rate) |
| Antibiotic | Guyot (120% of MIC₅₀) |
| Inducer | Joshi (12-hourly reservoir swap), Stacey (manual spike at `z = 21y − 20x`) |
| **Darkness** | Saeed (8 h dark → light → 4 h dark, to avoid photobleaching) |

They all want the same primitive: **a scheduled or feedback-driven trajectory for one actuator.**
Do not build a media-only feature.

### 3.2 Design guidance

- **Adopt Pioreactor's Experiment Profile schema rather than inventing one** (**SOURCED**; review
  §5). Load-bearing elements: quoted `version:` string, `metadata`, a `common:` block plus
  per-reactor overrides (maps onto M0–M4), actions `start/stop/pause/resume/update/log/when/repeat`,
  `t:` offsets with unit suffixes, `if:` conditions over live state, `${{ }}` interpolation, and
  helpers like `hours_elapsed()`.
- **`when: wait_until:`** (fire once, the first time a condition becomes true) is the construct
  that covers Wenk's staged ramps and Joshi's timed swaps.
- **A dry-run mode is not optional.** A scheduled program you cannot rehearse is one nobody will
  trust with a 150-day run. Log what it *would* have done.
- **Cumulative-volume interlock is mandatory** — a user-set maximum with a safety margin, enforced
  in the control thread, plus a running `voladded` accumulator. Copied from the published pH mod
  (`beckham-lab/Chi.Bio.pH`), which is the same class of guard as the watchdog and `valid=0`.
- **Prior art to borrow the design from, not the diff:** `ljm176/ChiBio` implements a two-reservoir
  ratio ramp inside `RegulateOD` (`Pump1 × (1−ratio)`, `Pump3 × ratio`). **Its growth-rate gating
  is written but dead** — `targetMet` is computed and never used; the ratio advances on a bare
  10-cycle timer. There is also unreachable code after `return`.
- **Steel's own recommended architecture for dosing** (**SOURCED**, forum 2020): *"one jar of
  normal media, and one jar of media + antibiotic, and mix the relative inflow fraction from each.
  This way you avoid having to dispense very small and precise volumes."* Ratio mixing, not
  micro-dosing — because of the pump-resolution problem in §6.1.

### 3.3 The morbidostat falls out nearly free

Once §3.1–3.2 exist. **A six-year-old, twice-asked, never-delivered forum request** (opened June
2020, re-asked April 2026, unanswered); Pioreactor ships `PID Morbidostat` as stock.

Use the control law **Steel's own lab published** (Corrao/Abrahams/Steel 2024, review §2.1):

- **PI on growth rate**, setpoint at **≈1/3 of the uninhibited baseline** (their theory says ~½ is
  near-optimal across the parameter range).
- **Exponentiate the controller output** — the non-obvious part. Adaptation proceeds
  *multiplicatively* in absolute stressor level, so a linear output ramps far too slowly at the top
  of the range.
- Report the actuator as a **fraction of maximum deliverable power**, so saturation is visible and
  the run has a defined endpoint.
- **Make the actuator pluggable:** pump ratio (drug) *or* UV intensity. Closing the loop on growth
  rate also neatly sidesteps the fact that the UV LED ships with no dosimetry at all.

---

## 4. The fluorescence track

**Scope it as two separable deliverables. (a) gates (b).** Do not start (b) first — comparable
units built on an untrustworthy signal are worse than no units.

### 4.1 (a) Trustworthiness

- **Matched non-fluorescent-control subtraction as a first-class FP mode.** Note for framing: this
  is **the vendor's own lab protocol** (**SOURCED**, chi.bio forum Nov 2024, absent from the
  manual): *"measure a 'zero' signal for each reactor… putting the same non-fluorescent sample in
  each (i.e. just cells + media)… Then, we subtract that zero from the experimental data to bring
  them to a common baseline. Doing this we find we can get very reproducible results."* Implementing
  it aligns the fork with vendor practice rather than diverging from it.
- **Pre-induction baseline subtraction** as the standard background rule: the mean of the 30 min
  *before* induction, subtracted from all values (Stacey/Steel 2026). Independently the same
  "induce from a zero baseline" rule the metrology paper recommends.
- **Cross-channel bleed-through correction** for the GFP+RFP pair — this fork has none.
  `mScarlet = Red − (Red:Green ratio) × Green`, the ratio taken from a window where GFP is on and
  mScarlet off. Using 595/670 avoids the correction but is noisier (Stacey/Steel).
- **[GUI] Sub-detectability warning.** Quote the vendor's own floor rather than hedging:
  *"if it is <0.5% of 'very bright' it will be difficult to measure"*. Pair with the **media
  warning** — LB is *"massively autofluorescent"*, use M9 — which Steel repeats in three threads.
  State explicitly that **raising gain or LED power does not help** (it scales signal and
  background together); the UI must not imply it will.
- **Finish the saturation guard properly** — §1.1, §1.2, and retune `_FP_BASE_NEAR_SATURATION`
  toward ams' documented 87.5%-of-full-scale (57343) expressed as a *fraction of computed full
  scale*, not a bare constant.
- **±10 nm tolerance on the Stokes-shift arithmetic** (§1.2).

### 4.2 (b) Comparability — only after (a)

- **MEFL·particle⁻¹ units**, using Díaz-Iza et al. 2025's two-stage structure (**SOURCED**, with
  public code at `sb2cl/MDPI2025-Calibration_Chibio`): an expensive **once-only, off-device**
  bead/fluorescein calibration against a reference instrument, plus a **cheap on-device
  re-calibration that only needs an ordinary culture**.
- **The trap worth encoding in the UI:** normalise by the **molecular brightness of the fluorophore
  actually present** — 597.5 for fluorescein *during calibration*, `B_GFP` when measuring cells.
  Storing a per-FP-slot brightness alongside the ex/em pair makes the error impossible.
- **Their automated wizard trick:** dilute continuously to a preset **sensor-value marker**, not to
  a target volume — explicitly because of *"the limited accuracy of the pumps when handling small
  liquid volumes"*. Four reads averaged per point, then re-fit in place. Directly implementable on
  this fork's existing pump + `measure_od` primitives.
- **Do not regress the per-reactor blank.** Their OD blank is hard-coded (`blank = 20909.33`),
  making their calibration effectively single-reactor. This fork's `CalibrateOD` / `OD0['target']`
  is better on that axis.
- **Caveat (SOURCED, Sambruna Fig. 5C):** a per-device **scalar** is *not* sufficient — the
  correction is concentration-dependent, showing *"non-trivial device-specific concentration trends
  that cannot be corrected by a simple additive offset"*.
- **Two other published recipes to read first:** Lee/Steel 2025 fit a per-reactor **offset +
  scaling factor** against a dilution series of filter-sterilised supernatant (recorded "after
  stirring 5 s and settling 5 s, mimicking experimental conditions"); Stacey/Steel 2026 adapt
  **FPCountR** to a per-reactor linear a.u. → **molar intracellular concentration**.

### 4.3 ⚠ What this changes for the *pending* matched-control experiment

`docs/fluorescence-control-prep-plan.md` and `docs/fluorescence-control-runbook.md` already specify
a five-reactor matched non-fluorescent-control run. The audit does not invalidate them, but
**check these four points before the run** — two are potential data-losing issues:

1. **Will the run capture raw emission counts?** If the FP logging channel records only emit/base
   ratios, the dataset **cannot support matched-control subtraction retrospectively** (§2.1). The
   runbook's per-scan EEM JSON capture mitigates this at the ladder points; the continuous FP
   channel is the exposure. **Either land §2.1 first, or confirm the EEM captures suffice for the
   analysis you intend.**
2. **Blank protocol.** The audit recovered two upgrades (**SOURCED**): the *accurate* procedure is
   buried in the manual's Troubleshooting section, not §3.2 — blank **in situ, at temperature, with
   stirring stopped**, then pipette cells in through the lid; Steel quantifies the payoff as
   *"typically reduce variability by more than 50%"*. And Stacey/Steel run **a second 15-minute
   period purely to confirm blank stability, re-blanking if it drifted**. Cheap insurance on a run
   whose whole point is a subtraction.
3. **GFP emission band.** Steel's supplement S1P explicitly compared 510 vs 550 nm and found
   *"a significantly improved signal for larger measurement wavelength (550 nm)"* for GFP. The
   fork's V2 caveat currently recommends LEDB→nm510 as least-bad. Worth checking what
   `recommend_fp_settings` returns and whether nm550 is being under-weighted.
4. **The turbidostat is the worst case for the ratiometric readout.** A QUT thesis (**SOURCED**,
   review §2.9) reports the onboard GFP was **flat during turbidostat steady state**, with real
   separation appearing only once dilution stopped and density climbed. If the control experiment
   runs in a fixed-OD mode, expect the *ratiometric* channel to look dead — that is the documented
   signature, not a failed experiment. Plan the analysis around raw + control, not the ratio.

---

## 5. Orchestration — an API, and why it is a documentation problem

**Promoted, and for an inverted reason.** Revision 1 ranked this on ReacSight's *success*. The
stronger case is a *failure* (**SOURCED**, review §2.3): a leading control group closed a
1-minute-cadence real-time loop by **sharing a CSV file over SFTP** — on a device that is already
a Flask HTTP server on the local network. Meanwhile ReacSight built an entire orchestration
framework on exactly that HTTP surface, and JHU APL federated 16 reactors over REST while keeping
the 8-per-controller boundary.

**The capability exists and is not discoverable.** That is as much a docs problem as an API one.

**Hard requirement revision 1 did not capture:** the API must be **explicitly addressed per `M`**
and must **not** depend on `changeDevice` — otherwise two physically coupled reactors cannot be
driven from one process, and the `single-owner-device-scripts` constraint makes a linked pair
impossible. Minimum viable surface:

- `GET` a measurement snapshot (largely `/getSysdata/` already).
- `POST` a per-reactor actuator setpoint **with an expiry**, so a dead orchestrator fails safe.
- Document that the cadence is **~1 minute**, and that measurement routes are not reentrant —
  firing faster than ~2 s yields `raw=0` with `valid=1` (see `measurement-routes-not-reentrant`).

**Prior art:** ReacSight's added route set (`/OD/<M-list>`, `/pumps/dilute/<M-list>`, `/stir`,
`/thermostat`, `/temperature`, `/version`) with pipe-joined reactor lists and pipe-joined
`rid_value` responses, one thread per reactor with a 100 ms stagger. Crude, but it works over
exactly this codebase.

---

## 6. Robustness and long-run survival

### 6.1 The pump layer is the least trusted subsystem

**Four independent groups routed around it entirely** (**SOURCED**, review §7 TL;DR item 4): manual
10 mL pipetting (*"the pumping rate was not fast enough"*), 12-hourly reservoir swaps, an external
Ismatec pump, and syringe sampling through a septum. Three more complain about dosing resolution:
the pH mod's **fixed pulse volume of 30–45 ± 10 µL varying per pump and per titrant**, the control
group's **peristaltic backflow that "reduce[s] control input resolution at low actuation levels"**,
and upstream's own PII second integrator existing to compensate degraded pump suction.

Actions, cheapest first:

- **Surface, don't silently raise, the `0.02` clamp.** `if(Pump1>0.02): Pump1=0.02` is an
  undocumented magic number. Make it a named, per-reactor, documented setting; **display the
  resulting maximum achievable dilution rate**; warn when a requested OD band or step is
  unreachable. Forum confirms *"You could increase that"* — but it is a software limit, so people
  should be able to see it before replacing hardware.
- **Steal the "test flow rate" button** from the pH mod: fire exactly one pulse so the user can
  weigh it, then store the measured per-pump, per-line, per-fluid volume in `sysData` and use it
  for a running `voladded`. There is no liquid feedback loop, so calibration is the only route to
  accuracy. Vendor position: *"we do not have an approximate calibration"*; *"might vary by up to
  50% between pump heads"*.
- **Sub-cycle pulse metering** for flows below one on-pulse per cycle (`colabbear`): within each
  period, run `period × |target|` and idle the remainder. Pairs with §1.4.
- **Bus-quiet windows for short actuations.** A 400 µs pump pulse stretched by a competing I²C read
  is a dosing error. This fork has the right primitive (the global `lock`) but no notion of
  "reserve the bus for this actuation". ⚠ **The published implementation of this idea is broken** —
  `beckham-lab/Chi.Bio.pH` assigns `pHControlPumpFlag` without a `global`, so its guard in `I2CCom`
  is dead code. Do not copy it blind.

### 6.2 Freshness, not just validity

**The missing half of the `valid=0` design.** Keeping the last-known value is **correct for the UI
and wrong for `RegulateOD`** — nothing currently stops a pump firing on a value that has been stale
for an hour. Both major peer platforms formalised this (**SOURCED**, review §5):

- Pioreactor: `STALE_READING_LIMIT = 5 min`, and `latest_od` is a **property that raises** rather
  than returning stale data.
- evolver-ng: `skip_control_on_read_failure`; controllers only **propose**, a separate
  `commit_proposals()` actuates, and `abort()` disables control and turns every effector off.

**Action:** timestamp every reading; have `RegulateOD` and `Thermostat` decline-and-warn on stale
or invalid input; put actuation behind a distinct commit step. This composes with the existing
sensor-failure semantics rather than replacing them.

### 6.3 Persist the blank; automate blanking

- **Persist** the OD blank (and any future calibration) across restarts. Every multi-week workload
  in the corpus — 150-day ALE, 250-generation consortia, 100-generation yeast — depends on it.
  `sysData`/`sysDevices` is already a *serializable-vs-not* axis; add a *survives-restart* axis.
- **Automate** blanking (`Janmorlock/ChiBio`): stir on 1 s → stir off → **settle 5 s** → **5×
  `MeasureOD`** → mean, storing `OD0['std']`. This simultaneously fixes the manual-blank friction,
  respects the ≥5 s read spacing this fork already documented, and yields a **per-blank quality
  number** that makes the §7.1 calibration question testable.

### 6.4 Fouling and contamination alarms — computable from data already logged

No new hardware (**SOURCED**, review §5, §1.2):

- **Stuck-OD alarm.** After each `RegulateOD` pump event, check OD actually fell by roughly the
  commanded dilution. Toprak's morbidostat troubleshooting names *"OD does not change after media
  injections"* → **biofilms on the inner wall** as *the* wall-growth signature.
- **Runaway pump rate at a stable OD setpoint** is the same signal from the other direction —
  Steel's supplement S1O derives it: as biofilm accumulates the required input rate → ∞, and once
  the pump saturates **OD drifts above setpoint**.
- **Spread spikes.** This fork already computes a 3× median **and spread** — surface it. Clumping
  shows up here first.
- **Log the *inferred* dilution per cycle** (`final_OD[n] / initial_OD[n+1]`), not just the pump
  command. Makes the pump self-calibrating and gives free QC on tubing wear.
- **Biofilm-inflated growth rate is a silent data corruptor** (Lee/Steel had to switch to a ΔlapA
  *P. putida* strain): wall growth escapes dilution and inflates the apparent growth rate. A check
  against the strain's known µmax would flag it.

### 6.5 Other long-run items

- **Thread exhaustion is a documented upstream failure** — `RuntimeError: can't start new thread`
  inside `runWatchdog` after ~1 week, unresolved upstream. This fork's `threadCount` supersession +
  `running` flag are the mitigation; consider logging live thread count into the events log so a
  recurrence is diagnosable rather than mysterious.
- **The BeagleBone has no RTC and drifts.** Push the host clock as part of the deploy loop
  (`tauzn-clock`'s `tools/set_time.sh`: `ssh root@ChiBio date --set=…`). Silently corrupts long-run
  timestamps otherwise.
- **Structured logging with `DeviceID` in every message**, a log level, and rotation. Five reactors
  over a multi-day run make bare `M3` ambiguous and scrollback lossy.
- **Extend the events log to operator actions** — sampling events (label, auto-number, volume,
  wall-clock + elapsed) and an explicit **inoculation marker**, so t=0 for biology is
  distinguishable from t=0 for the software. This fork already has `logEvent`; this points it at
  the workflow everyone actually uses (offline cytometry/HPLC on grab samples).
- **Per-reactor quarantine instead of whole-process death** on repeated mux failure — **only** if
  it first calls `turnEverythingOff` for that reactor and preserves the global kill for a wedged
  bus. See §9 before touching this. Check whether this rig's boards have the hardware mux-reset
  chip Steel says later LabMaker boards carry.

---

## 7. Open scientific questions on this rig

### 7.1 Does reactor identity actually affect the OD math here?

`CLAUDE.md` says no code path makes it so, therefore accuracy is purely a function of blanking.
**That is true of the codebase and untested on this rig** — and three independent groups disagree
in code (**VERIFIED** from their repos, review §4.2):

| Group | Functional form | Spread |
|---|---|---|
| Imperial GBS | quadratic `a·raw² + b·raw` | quad 0.086–0.268 (~3×), lin 0.537–1.077 (2×), r² 0.90–0.99, **n=16** |
| Inria/ReacSight | cubic with constant term | all four coefficients differ, **n=8** |
| Mitri lab | exponential `m·exp(−t·OD)` | per reactor, calibrated to **OD ~6**, **n=8** |

**32 reactors of evidence.** The claim may still be adequate at OD ≈ 0.5.

**The experiment that settles it:** a 6–8 point dilution series on **two** reactors, blanked
normally, fitted independently. If the fits differ beyond the blank's σ (which §6.3 would give
you), adopt a per-reactor coefficient file. Cheap, half a day, and it either retires the question
or changes how every OD number on this rig should be read.

### 7.2 Does reading OD through `CLEAR` matter?

ReacSight changed their OD read to the **`nm670` filter specifically so blue optogenetic light
could not contaminate it**. This fork reads `CLEAR`. **If any LED is on during an OD read, this is
a correctness bug, not an enhancement.** Bench check: blank with an LED at 0.1 and compare.

Related and independent (**SOURCED**): a single-molecule group deliberately chose the 650 nm laser
over the LED *"to prevent accidental photoactivation of PAmCherry2.1 due to the large emission
spectrum of the LED"* — the measurement light source is a **photobiological perturbation** for
photosensitive constructs, not just an optics choice.

---

## 8. Briefing for bench work — what the corpus says about running this machine

For an agent planning experiments rather than writing code. All **SOURCED** from the corpus unless
marked.

### 8.1 Operating envelopes actually used

| Parameter | Range in the corpus | Notes |
|---|---|---|
| **OD setpoint** | **0.3–0.6 is the standard characterisation envelope** | Joshi 0.5, Stacey 0.5, Jessen 0.5, Deng 0.5/0.3, Allan 0.3 |
| | 0.75 (7-day ALE), 0.8 → 0.6 (2-week evolution), 1.0 ± 0.04 (the R tool's worked example) | Higher is used, but for evolution not characterisation |
| | Cap at **0.8**; one group discards all data above it as near-saturation | And Steel: *"at 37 degrees I have found best regularity at OD~0.1 and below"* |
| | A thesis reported end-of-run **OD ≈ 7.5** with no warning | Far outside the blanked range — the UI does not flag this |
| **Working volume** | 12–25 mL; **20 mL typical**; **~15 mL minimum** (set by the optical path) | 30 mL flat-bottom vial |
| **Stir** | 0.5–0.8; vendor-recommended band **0.6–0.7** | Denton used 0.2 for a cell-free reaction |
| **Temperature** | 20 °C, 28, 30, 37, and **50 °C** (thermophiles, worked) | Parts rated ≥70 °C; **cooling is passive only** |
| **Cadence** | **1 min** is the platform's control period, and external controllers inherit it | |
| **Run length** | 18 h → 150 days; 7 d and 2 weeks are common | The *published* demo is 1.7 d — which is how outsiders score it |

### 8.2 Which readouts to trust

| Readout | Trust | Basis |
|---|---|---|
| **Growth rate from OD** | **High — this is what people publish.** Six papers derive it four different ways | Two open-source estimators exist: `GOFFREDOpy` (Bayesian, turbidostat-aware) and LANL's `chemostat_regression` (R + ggplot2 + Shiny) |
| **OD, relative** | High within a run, after a good blank | ~2% loop spec; forum reality **±10%** at OD 0.4 |
| **OD, absolute (as OD600)** | **Low without a per-setup conversion.** Every lab re-derives one by hand | One lab measured Chi.Bio-AU ≈ 2× OD600. Steel: chasing cross-instrument agreement is *"a false sense of security"* |
| **FP, ratiometric emit÷Clear** | **Do not use for dim FPs.** Worst case is **turbidostat steady state** | Also drifts ~1.35× per 4× OD change, per Steel's own supplement |
| **FP, raw + matched control** | The viable path | Vendor's own lab protocol |
| **Temperature** | ±0.2 °C is the **sensor spec, and only over 36–38 °C** (±0.3 outside, ±0.5 further) | Not a loop guarantee |
| **LED intensity** | **Uncalibrated arbitrary units.** No photon-flux meaning | See §8.4 |

### 8.3 Protocol details worth adopting

- **Blanking:** in situ, at temperature, stirring stopped, then pipette cells through the lid
  (*"reduce variability by more than 50%"*); then a **second 15-min run to confirm blank
  stability**, re-blanking if it drifted.
- **Media:** M9, not LB. LB is *"massively autofluorescent"* and will wash out any FP measurement.
- **Sterility (the fork currently documents none).** Two independent groups converged on: assemble
  the passive fluidic circuit (glassware + tubing + air filters) connected to the medium bottle,
  **autoclave it as one closed unit**, install, then seat dedicated tubing sections into the pump
  heads **without opening the circuit**. Vendor protocol is 10 s of alcohol per tube then media,
  storing tubes full of **70% ethanol**. Two known contamination pathways: **pump-head backflow
  into the fresh-media bottle** when the seal is poor (fix: tape, or a McMaster 7757K41 check
  valve), and **wall growth**, which is the binding constraint on run length.
- **Aeration:** there is **no aeration control in the software at all**. One group's active
  aquarium-pump aeration was *actively harmful* (8 h lag, near-zero product) — passive membrane
  aeration won. Others add 0.22 µm filtered vents on **both** the reactor lid and the media bottle
  (the waste pump pulls headspace air out, so the culture needs make-up air).
- **Stir-bar geometry is a first-order experimental variable, and invisible to software.** A
  cylindrical vs tablet bar gave **~6× different biomass** in the same reactor at the same settings,
  attributed to shear. At minimum, record the stir setting in the metadata sidecar and note the
  hazard in the runbook.
- **Reactor-to-reactor spread is real:** two nominally identical reactors under identical optimised
  conditions differed by **~57% in product**.

### 8.4 Light and optogenetics

- **Intensity is in arbitrary units with no photon-flux calibration.** For one common green-light
  sensor, the **lowest testable setting (0.003 a.u.) already matched the optimum** established on a
  calibrated light plate apparatus, and **every higher setting reduced expression** through
  phototoxicity. A control spanning three orders of magnitude whose useful region sits at the very
  bottom needs a **log-scaled input**, not a linear slider. **[GUI]**
- Vendor warning: *"avoid running the LEDs for prolonged periods at or near maximum power…
  it is fine to run multiple LEDs continuously at power ∼0.1"*; Steel's supplement says
  *"generally each LED is run at 5∼10% of its maximal output"* and total optical output should
  stay below 1.5 W.
- **The discrete LED palette is a hard experimental constraint** that people report in print —
  one group chose their wavelength *"from the available Chi.Bio LEDs as the shortest wavelength
  that supported stable assay operation without measurable chromophore photobleaching."* A UI
  showing each LED's true centre wavelength (and, on V2, the missing ~488 nm) is doing real
  scientific work. **[GUI]**
- **Photobleaching is managed by scheduling darkness** (8 h dark → light → 4 h dark), hand-run
  today. Another argument for §3.

### 8.5 Consumables — externally corroborated

- **Vial:** 30 mL flat-bottom, **Fisher 11593532** — used by three independent groups, a de facto
  standard. Diameter must be **≤24.5 mm** to fit (the Hardware page's "25 mm" is wrong, and a group
  had to extract vials with pliers).
- **Pump tubing:** silicone **2.5 mm ID / 4.5 mm OD** (bore 2.5, wall 1.0; Altec 01-93-1416/20) —
  **independently confirms this repo's `tubing-eu-sourcing` memory.** Departing by *"more than
  0.1 mm"* makes pumps jam or fail to seal; any substitute must keep **2 mm total wall thickness**.
  Replace after several months of heavy operation.
- **Lids leak, and it is a software-reliability issue.** Add a **15 mm ID × 18 mm OD FKM O-ring**.
  *"If you are having issues with crashing then 95% probability the issue is the seal of the lid
  onto the glass for the vial"* — moisture reaches the sensing tracks and kills the run.
- **The top liquid-level sensing ring is *"at least 80% of the time the offender"*** for
  "Failed to recover multiplexer", is trigger-happy with humidity, and is **physically
  disconnectable** (remove the side panels; disconnect two wires).
- **Laser diode:** the vendor's own BOM warns some `ADL65052TL` suppliers ship *"as much as 10%
  defective stock"*.

### 8.6 Two hardware extension routes, both published

- **The expansion header is an I²C stub** (SDA4/SCL5): *"any I²C device can be implemented over
  this interface."* The published pH mod adds a sensor + its own control loop entirely within the
  architecture — new device on the mux, reads through `I2CCom`, its own thread on the `threadCount`
  pattern, its own `sysData` sub-dict, CSV columns, routes, in-UI calibration, and a **cumulative
  volume interlock**. **The 3.3 V rail is the scaling limit, not the bus** (~3 Atlas EZO circuits
  per external supply; stagger reads).
- ⚠ **`I2CCom`'s signature is too narrow for string payloads** — the pH mod worked around it with
  `if hl<20 and device != 'pHProbe'`. If a peripheral is ever added here, widen the signature
  properly rather than special-casing a device name.

---

## 9. Do not change these — now with citations

Each of these looks like a smell and is not.

- **The deliberate whole-system crash on unrecoverable mux failure is designed.** Steel:
  *"there is a hardware safety system that is able to hard-disable all of the electronics/pumps in
  the whole system… if one of the pumps was left on… this would then be a physical shut-off…
  By doing what you suggest (preventing them from crashing together) you will open the possibility
  that if one of the pumps gets turned on and left on and overflows, it will now STAY ON. So,
  proceed at your own peril."* This fork's *"Don't 'fix' these by swallowing them"* convention is
  **vendor-endorsed**.
- **The PII's second integrator is not cruft** — it exists solely to compensate a pump with
  *"temporarily reduced suction"* from badly seated tubing. An external control group independently
  described it as compensating *"the effect of faulty gaskets in the pumps."*
- **Ratiometric as the default until the FP rework lands.** Steel confirms it removes *"(by say
  ~90%)"* the OD dependence. Imperfect, not useless.
- **The mux hard-reset via GPIO** is the sanctioned recovery path on V1.2+ boards.
- **`--timeout 300` in `cb.sh`** is independently corroborated by two upstream issues; the default
  30 s silently wipes RAM-only experiment state.
- **Binding to `192.168.7.2`** (the USB-gadget address) is the *supported* path. Serving the UI
  over Ethernet is a known-unstable route upstream — *"implemented by someone else (not me) and is
  not used in our lab, so I can't say that I have ironed out all the bugs in it."*
- **`get_spectrum` must not auto-range** — it feeds `CharacteriseDevice`, which compares raw counts
  across a power sweep. (Another fork added auto-gain there; that is a divergent design choice, not
  a fix.)
- **Bounded replication, the I²C chokepoint, `valid=0` semantics, per-reactor blanking, and the MPC
  heater model** all match what the Forman primer endorses and what Steel's supplement describes.

---

## 10. Where this fork is already ahead

Useful context when deciding what to upstream or publish.

- **`CHIBIO_SIM=1` answers a question asked twice on the forum and never solved upstream** —
  Steel's 2022 answer was *"a group at Imperial… decided that it was easier to just get a second
  beaglebone/chi.bio reactor and have that sitting on a bench as a test dummy."* Off-device modes
  have now been independently reinvented four times across the fork network; this is the strongest
  of them. **If anything here is worth upstreaming after the CSV fix, it is this.**
- **The `csv.DictWriter` refactor is the structural fix for a bug that cost the upstream community
  ~22 months of headerless data** on every V2 device — reported, un-reproduced by the maintainer,
  correctly diagnosed in a still-open PR, and finally fixed upstream by **this repo's PR #19**.
- **`git merge-base` confirms this fork is at upstream HEAD.** There is nothing to pull; upstream
  has been effectively dormant since 2024.
- **Documentation-wise the fork is ahead of the vendor.** The forum's most-repeated unanswered
  request is for a software readme/API, still promised as of 2026-04-13.

---

## 11. Unread sources, ranked

1. **Methods Mol Biol 3041:145–195** — Stacey, Lee, Gallup, Csibra, Papachristodoulou, Steel,
   Sechkar 2026, *"Characterization of Synthetic Gene Circuits with Absolute Quantification in
   Continuous Culture."* `10.1007/978-1-0716-5304-3_8`. **The source lab's own 51-page Chi.Bio
   calibration protocol with troubleshooting.** Paywalled, no abstract exposed.
   **Get this before starting §4.** Companion chapter `…_13` likewise.
2. **Pen, Nunn & Goyal 2021**, ACS Synth Biol 10(4):766–777, `10.1021/acssynbio.0c00574` — a 25 mL
   turbidostat built around high-dynamic-range multicolour in-situ fluorescence, i.e. exactly where
   Chi.Bio is weak. Closed access, no preprint, no repository copy.
3. **Supplementary information was not fetched for any paper** in the audit. Several relevant
   numbers live there — Lee's Chi.Bio fluorescence characterisation, the LED light-intensity
   calibration, Stacey's per-reactor conversion curves.
4. **The Sambruna code repository**, promised on GitHub but not yet published. Their acquisition
   routines are the closest published analogue to `chibio_fluorescence`, and their bead protocol is
   a ready-made per-device calibration recipe. **Worth re-checking periodically.**
5. **ams SMUX/calibration application notes** — `look.ams-osram.com` serves an empty body;
   distributors mirror only the datasheet.
6. **ProQuest / CORE** were not swept. Three dissertations surfaced from OpenAlex alone, and the
   two that were read were the most candid failure accounts in the entire corpus — so more are
   likely. No Steel-lab DPhil thesis was found in Oxford ORA, which is surprising.

---

## 12. Suggested sequencing

Dependencies matter more than priority here.

**Phase 1 — small, verified, no design work.** §1.3 + §1.4 (pump bugs, adjacent lines), then
§1.1 + §1.2 (AS7341 saturation, same module). Off-device tests exist for the patterns; device
self-test after. **Do §1.1 before any FP work**, since a misdetected LED version invalidates
everything downstream.

**Phase 2 — schema, before the next experiment.** §2.1 raw OD + raw FP columns, §2.2 sidecar
optical config. This is the gate on §4 producing usable data.

**Phase 3 — pick one of two tracks** depending on whether the next work is bench or build:

- *Bench next:* §6.3 (automated + persistent blanking) → §4.3 checks → run the matched-control
  experiment → §4.1.
- *Build next:* §3 (scheduled dosing / profiles) → §3.3 (morbidostat falls out) → §5 (API).

**Phase 4 — robustness.** §6.2 freshness, §6.4 fouling alarms, §6.5 logging and events.

**Standing:** §7.1 (the two-reactor dilution series) is half a day and either retires or changes a
documented assumption. Do it whenever the rig is free.

---

*Provenance: this document summarises `docs/chibio-usage-literature-review.md` rev. 2 (2026-08-11),
which supersedes rev. 1 (2026-07-18) and records 16 corrections to it in its §0. Where the two
disagree, the review is authoritative and this document is the error. Where the repo's code and
either document disagree, **the code and the device are authoritative** — see the hardware-first
rule in `CLAUDE.md`.*
