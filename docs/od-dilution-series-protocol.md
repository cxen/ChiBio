# OD dilution-series protocol — is blanking really all that calibrates OD?

**Status:** planned, not yet run. Written 2026-08-13, for the window while the rig is empty
between Run 0 and Run 1.

**Read `INVARIANTS.md` first**, especially §4 (single-owner rule), §6 (stirring, and loading vials
with stir OFF) and §7 (measurement). This protocol touches nothing but Stir and the OD laser, and
writes no calibration until the very last step — but it is still bench work on a live server.

---

## 1. The question, and why it is open

`CLAUDE.md` states that no code path makes reactor identity change the OD math: the quadratic
constants are shared by all eight reactors from one template (`chibio_state.py:42`,
`LASERa = 0.226`, `LASERb = 1.833`), the per-`M0`–`M3` `CF` constants are inherited dead code, and
the only per-reactor term is the blank `OD0['target']` you set with `CalibrateOD`. That is a true
statement *about this codebase*. It is **not** a measured statement about this rig.

Three independent groups disagree with it in code (review §4.2, **32 reactors of evidence**):

| Group | Form they fitted | Spread across their reactors |
|---|---|---|
| Imperial GBS (`zoltuz@imperial_GBS`) | quadratic `a·raw² + b·raw`, per reactor | quad 0.086–0.268 (**~3×**), lin 0.537–1.077 (2×), n=16 |
| Inria InBio (ReacSight) | cubic with a constant term | all four coefficients differ, n=8 |
| Mitri lab (`nahanoo/ChiBioFlow`) | exponential `m·exp(−t·OD)`, to OD ~6 | fitted per reactor, n=8 |

Each of them found it worth the effort to fit a *different curve per reactor*. None of them
published the residual you'd get from *not* doing it, so their work says the question is live —
not that our answer is wrong.

**We already have one measurement that leans the same way.** Per-reactor OD blank spread on the
same medium was **1.35×** (11651–15764 counts, CV 12.3 %, four reactors, 2026-08-13). Blanking
absorbs a constant multiplier by construction; what it cannot absorb is a *difference in curvature*
— i.e. a reactor whose transmission falls off differently as cells accumulate. Only a series over a
range of densities can see that.

**What this protocol settles.** For each reactor, a set of (raw transmission counts, reference OD)
pairs over a decade of density, from which:

1. a per-reactor fit, compared against the shared-constant prediction — **if the per-reactor fits
   agree within the blank's σ, the `CLAUDE.md` claim is confirmed for this rig and the assumption
   stops being an assumption**; if they diverge, we adopt a per-reactor coefficient file, exactly as
   the three groups above did;
2. the **Chi.Bio ↔ cuvette scale as a curve rather than a point**. Run 0 gave 2.81 ± 0.22 (CV 7.7 %)
   from M0/M1/M4 at *one* density, n=3 — provisional by construction, since a single density cannot
   distinguish a scale factor from a curvature mismatch;
3. the density at which each reactor's transmission stops being usable (the upper end of the range
   the turbidostat can honestly run in).

**What it does not settle:** M0's slow growth. The Run 0 cuvette cross-check already showed M0
genuinely had fewer cells, so that is biology or vial handling, not optics (`INVARIANTS.md` §6).
M0 is still worth including here — a reactor that reads oddly *and* grows oddly is a different
story from one that only grows oddly — but do not expect this to explain it.

---

## 2. The measurement the device actually takes

Mirror it exactly, or the calibration is taken under different optical conditions than the data it
will calibrate. `runExperiment` (`chibio_experiment.py:356`) does:

```
stir OFF  →  sleep 5.0 s  →  3 × measure_od inside one measurement mutex  →  median + spread
```

and `measure_od` computes, for `LASER650`:

```
R  = log10( OD0['target'] / OD0['raw'] )        # target = the blank, raw = this read's counts
OD = LASERb·R + LASERa·R²                       # = 1.833·R + 0.226·R²
```

So **`OD0['raw']` is the primitive** — it is the only number this protocol needs from the device.
Everything else is arithmetic we can redo offline against any fit we like. Record `raw` (and
`rawCorrected`, the dark-subtracted variant), not `OD['current']`.

**Do not re-blank between levels.** The blank is a fixed reference; changing it mid-series destroys
the series. Blank once, at the start, on clean medium (§4.2), and leave it.

---

## 3. Design

**Direct dilutions from one stock, not a serial dilution.** A serial dilution compounds pipetting
error monotonically down the series — precisely the shape of a spurious curvature, which is the
thing being measured. Prepare each level independently from one dense stock.

**One suspension per level, split across reactors.** At each level, every reactor is filled from
the *same* bulk tube, and the cuvette reading is taken from that same tube. This is what separates
per-reactor optics from per-reactor pipetting: if each reactor made its own dilution, a pipetting
difference would be indistinguishable from an optics difference — the exact confound.

**Scope.** The review's concrete test is *"a 6–8 point dilution series on two reactors"*. Take
**M1 and M3** as the required pair (the two clean growers from Run 0). Add M0 and M2 if the
suspension volume allows — the marginal cost is one vial fill per level, and four curves make the
"do they differ?" question far better posed than two.

**Levels.** Eight, spanning roughly OD 0.05 → 4 in cuvette units, weighted toward the top where the
curvature lives and where Run 0 actually ran (plateau 2.94):

| Level | Fraction of stock | Target cuvette OD (stock ≈ 5) |
|---|---|---|
| 1 | 1.00 | ~5 |
| 2 | 0.60 | ~3 |
| 3 | 0.36 | ~1.8 |
| 4 | 0.20 | ~1.0 |
| 5 | 0.12 | ~0.6 |
| 6 | 0.07 | ~0.35 |
| 7 | 0.04 | ~0.2 |
| 8 | 0.02 | ~0.1 |

Adjust the fractions to whatever the stock actually reads — the *measured* cuvette OD is the
reference, the nominal fraction is only a guide.

**Volume.** 20 mL working volume per vial (the Run 0 configuration; the laser path is at a fixed
height and this protocol is not the place to discover the minimum). Two reactors + a cuvette
aliquot ⇒ **~45 mL per level**, so a 50 mL falcon per level. Four reactors ⇒ ~85 mL per level, two
falcons or one 100 mL bottle. Stock needed = 20 mL × n_reactors × Σ(fractions) ≈ **2.4 vial-volumes
per reactor**, i.e. ~120 mL of OD-5 stock for two reactors, ~240 mL for four.

**Material.** Two defensible choices, and they answer slightly different questions:

- **Cells (MG1655 WT in M9 + 0.2 % glucose), heat-killed or ice-held.** The right material for the
  cuvette-scale deliverable, because that scale must be in cell units. Killing (or working cold and
  fast) matters: a growing stock changes density *during* the series, which writes a time trend
  into what should be a density trend. Cells also sediment — see §5.
- **A stable non-biological scatterer** (polystyrene microspheres, or formazin). Better for the
  per-reactor-optics question alone: no settling drift, no growth, indefinitely re-runnable. But
  its scattering is not *E. coli*'s, so it cannot give the cuvette scale.

If you can only do one, do **cells** — the cuvette scale is the deliverable with a downstream
consumer, and the optics question is answerable from the same data.

---

## 4. Procedure

### 4.1 Before anything

Single-owner rule: nothing else runs against the server while this is going.

```bash
ssh ChiBio
curl -s -X POST http://127.0.0.1:5000/scanDevices/all
curl -s http://127.0.0.1:5000/getSysdata/ | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['DeviceID'], d['present'], d['Version']['LED'])"
```

Confirm the reactors you intend to use scan **present**, and that no experiment is running
(`Experiment.ON == 0`). Never measure a reactor that isn't confirmed present
([[presence-detection-gotcha]]).

Heater **off** for the whole series — a warming vial convects, and convection is mixing you did not
ask for and cannot log.

### 4.2 Blank, once

Load each vial with **clean, cell-free medium** — the same M9 + 0.2 % glucose the stock is made in,
from the same batch. Stir OFF while loading (`INVARIANTS.md` §6: seating a vial with the stirrer
running is what causes clanking).

Then per reactor: stir on 60 s → stir off → 5 s → **5 × `MeasureOD`, spaced ≥ 8 s**, take the mean
of `OD0['raw']`, and record its standard deviation. **That σ is the yardstick the whole experiment
is judged against** — a per-reactor curve difference only counts if it exceeds it.

**Then check the blank held.** The source lab blanks, runs a further **15 minutes**, confirms the
blank is stable, and re-blanks if it moved (Stacey et al. 2026 Methods; review §9.4). We have
never done this, and a blank that drifts under the series invalidates every level measured after
it. Repeat the 5-read mean 15 min later; if it has moved by more than the σ you just measured,
re-blank and restart the clock. Two other details from the same protocol are worth adopting here:
they equilibrate temperature for 15 min *before* the first blank, and they clean vials with
ethanol **and dry them** — residual ethanol is a live suspect for M0's unexplained slow growth
(`INVARIANTS.md` §6) and costs nothing to eliminate.

```bash
curl -s -X POST http://127.0.0.1:5000/CalibrateOD/OD0/M1/<mean_raw>/0
```

`knownOD = 0` sets `OD0['target']` to the raw you pass, i.e. zero-at-blank. Verify it took (it must
no longer read 65000):

```bash
curl -s http://127.0.0.1:5000/getSysdata/ | python3 -c "import sys,json; print(json.load(sys.stdin)['OD0']['target'])"
```

Log each blank to the events sidecar automatically — `CalibrateOD` already does this.

### 4.3 Per level, descending from level 8 (most dilute) to level 1

Working dilute → dense means the small carryover between levels pushes each reading *up* the curve
in the same direction as the next level, rather than contaminating a dilute level with dense
residue. Rinse vials with medium between levels regardless.

1. Invert the bulk tube for that level 10× to homogenise.
2. Take the **cuvette reading immediately** — this is the reference, and it must be taken from the
   same homogenised tube, not from a vial that has been sitting.
3. Fill each vial to 20 mL from that tube, **stir off** while loading.
4. Stir **on**, 2 min, to homogenise in the vial.
5. Stir **off**, wait **5 s** (the device's own settle), then **3 × `MeasureOD`** on that reactor.
6. Record per read: `OD0['raw']`, `OD0['rawCorrected']`, `OD0['dark']`, `OD['valid']`,
   plus wall-clock time.
7. Repeat 4–6 for each reactor at this level. Interleave rather than finishing one reactor at a
   time, so any drift in the suspension is spread across reactors rather than loaded onto the last.
8. **Second cuvette reading** at the end of the level, from the same tube. The difference between
   the two cuvette readings is the level's own drift, and it bounds how much of any reactor-to-
   reactor difference is real.

### 4.4 After

Every output off. Empty and clean the vials. Archive the record file and md5 it, as with Run 0.

---

## 5. The two things that will corrupt this if ignored

**Sedimentation, which we have measured.** In a stationary vial, transmission rises **5–10 %
across three consecutive reads** in every reactor holding cells, and is flat (0.2 %) in a sterile
one (2026-08-13). That is a monotonic ramp *inside* one measurement window, and at high density it
is fast. Mitigations, all of them mandatory: the fixed 2 min stir before every level, the fixed 5 s
settle (not "about five seconds"), a fixed read spacing, and **recording the ramp rather than
averaging it away** — keep all three replicate values, not just the median, so the within-window
slope is in the data. If the three reads at a level span more than the blank σ, say so in the
record; that level is a range, not a point.

**Cuvette linearity.** A spectrophotometer is itself nonlinear above OD ~1 and the top of this
series is well past that. **Dilute the top levels into the cuvette's linear range and multiply
back** — do not read OD 5 directly and trust it. Record the cuvette dilution factor per level.
Getting this wrong writes a curvature into the *reference*, which would then be attributed to the
reactors: the exact failure this protocol exists to detect.

---

## 6. Analysis and the decision rule

For each reactor, with the blank `T₀` fixed:

```
R_i    = log10( T₀ / raw_i )              # per level i
OD_ref = cuvette OD × cuvette dilution    # the reference
```

1. **Plot `OD_ref` against `R`, per reactor, all on one axis.** This is the whole experiment in one
   figure. The shipped model is the single curve `OD = 1.833·R + 0.226·R²` for every reactor.
2. **Fit per reactor**, same quadratic form, unconstrained. Compare the coefficients and, more
   informatively, the *residuals of each reactor against the shared curve*.
3. **Decision:** if the per-reactor residuals stay within the blank σ propagated through the OD
   formula, the shared constants are adequate for this rig at this range — record that as a
   measured result and close review §4.2. If any reactor's residual exceeds it systematically
   (a trend, not scatter), adopt a per-reactor coefficient file, following Imperial GBS's
   `config/device_config.csv` layout rather than inventing one.
4. **Report the range.** The answer is almost certainly range-dependent — adequate at OD 0.5,
   diverging at OD 3. State the OD above which the shared constants stop holding, because that is
   the number that constrains how Run 1 is designed.
5. **Cuvette scale:** regress Chi.Bio OD on cuvette OD across the series. If it is a straight line
   through the origin, 2.81 ± 0.22 stands and gains error bars. If it curves, the single-density
   Run 0 number was measuring the local slope of a curve and should be retired, not refined.

**Report descriptively.** Tables of coefficients, residuals and ranges. The interpretation — what
to do about it — is step 3's decision rule, not a narrative.

---

## 7. Tooling

No script exists for this yet. The reads themselves are `POST /MeasureOD/<M>` followed by
`GET /getSysdata/`, exactly as `probe_cultures.py` and `probe_repeat.py` already do, and those two
are the templates to copy: they hold the single-owner rule, drive Stir for homogenisation, respect
the read spacing, and write one JSON record per run.

A `probe_dilution_series.py` would be worth having if the series is run more than once (and it
should be: once with cells for the scale, once with a stable scatterer to confirm the optics answer
without settling in the way). It cannot automate the bench half — filling vials and reading the
cuvette is manual — so its job is to prompt per level, then take and record the reads at a fixed
cadence.
