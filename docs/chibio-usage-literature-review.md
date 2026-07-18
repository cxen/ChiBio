# Chi.Bio in the wild — how others use it, and what it means for this fork

A literature review focused on one question: **how do people actually use the Chi.Bio
bioreactor — effectively or not — and what should we change in this fork as a result?**

Compiled 2026-07-18. Nine sources read in full (or as fully as access allowed); each was
read specifically for *usage, calibration, control strategy, hardware quirks, and lessons
for a software maintainer*, not for its biology. Where a source's deep detail lived in a
supplement that could not be fetched, that is flagged inline.

This fork = a divergent refactor of `HarrisonSteel/ChiBio` (Flask app on a BeagleBone
Black, I2C bus, OD turbidostat, PI+MPC thermostat, peristaltic pumps, optogenetics via
on-board LEDs, AS7341 spectrometer for OD + fluorescence).

---

## TL;DR — the actionable conclusions

1. **The onboard fluorescence readout is not quantitatively trustworthy for GFP-in-cells
   as currently normalized.** This is now documented consensus, not a one-off. Finishing
   the fluorescence path is the single highest-value piece of work this review surfaced.
2. **Programmed inducer/media dosing is a real capability gap.** Two independent groups
   worked around it manually. Scheduled media recipes + inducer ramps deserve to be
   first-class, not custom-program hacks.
3. **Closed-loop control is the platform's whole thesis** — every device paper and the
   optogenetics review converge on it. Preserve the fidelity targets (~2% OD, ±0.2 °C).
4. **Long unattended runs (weeks to months) are the norm.** Comms robustness, blank
   drift, and dense timestamped logging matter more than peak per-read accuracy.
5. **The architecture is already on the endorsed path** (I2C bus, bounded replication,
   watchdog, multiparameter-over-fidelity). Don't "fix" what the primer literally praises.
6. **Chi.Bio being a Flask/HTTP app is a feature to lean into** — ReacSight built a whole
   orchestration framework on exactly that. Add POST hooks + a declarative event layer.

---

## Source 1 — Colleagues' fluorescence-metrology paper (THE key result)

**Sambruna, Tallarico, Cosentino Lagomarsino.** *"Calibration standards and sensitivity
limits for fluorescence measurements with the Chi.Bio open-source bioreactor platform."*
bioRxiv, posted 2026-07-01.
<https://www.biorxiv.org/content/10.64898/2026.06.29.735387v1>

Uses the upstream `HarrisonSteel/ChiBio` software — the direct ancestor of this fork.
This is a **metrology paper**: is the AS7341-based fluorescence readout quantitatively
trustworthy? (OD calibration is well established; fluorescence never was.)

**Setup.** Fluorescence calibration microspheres (known ex/em, stable) + *fixed*
GFP-expressing *S. cerevisiae* (Rpl5-GFP) and *E. coli* (sfGFP), benchmarked against a
monochromator plate reader (Tecan Infinite 200 PRO). Five reactors on one shared
microcontroller (to quantify inter-device variability). **Thermostat and pumps disabled**;
ambient temp, no flow, static 20 mL vials. Spectrometer/fluorescence *only* — OD used
solely as a concentration reference.

**Findings (the valuable part):**
- **GFP falls below the detection limit.** Fixed GFP yeast were indistinguishable from
  wild-type (signal-to-background ≈ 1.0); *E. coli* showed only marginal separation. The
  plate reader resolved both easily → it's device sensitivity, not expression.
- **Root cause is optical architecture** (confirmed by Harrison Steel, pers. comm.):
  broad-spectrum LEDs leak excitation through the emission filters → a
  *concentration-dependent background*; the 90° LED–detector geometry adds a large
  scattering peak near the excitation wavelength. Worse when ex/em are close.
- **The built-in ratiometric normalization is flawed.** Emission ÷ Clear channel (the
  method from the original Chi.Bio paper) breaks at both ends: background dominates at low
  concentration; **the Clear channel saturates at 65535** at high density, offsetting the
  ratio. In dynamic experiments with periodic dilutions it "generates artifactual signal
  changes that can be mistaken for biological responses."
- **Inter-device variability** persists after normalization (KDE peak positions shift per
  device; net-signal / σ_device ≈ 3.3, not reliably above threshold). Microspheres stayed
  separable → it's a sensitivity floor, not breakage.
- **Raising gain and LED power did not help** — scales signal and background together.
- LB/rich-media autofluorescence inflates background.

**Recommended practice from the paper:**
- **Direct subtraction of a matched non-fluorescent control measured in the same reactor**
  beats ratiometric Clear-normalization (intercepts near zero, linear). Control must be
  same-device or cross-device calibrated.
- **Induce from a zero baseline** (start uninduced, subtract pre-induction baseline) rather
  than compare two steady states.
- **Per-device calibration against a fluorescent reference standard** before any
  cross-device comparison; verify expected signal on a sensitive instrument first.
- Settings used: beads gain ×512 / power 0.1; cells power 0.01 (higher didn't rescue GFP).
  Ex/em pairs 395/510 and 523/620 nm. Concentration binned at ΔOD=0.1; 1 OD₆₀₀ ≈ 3×10⁷
  cells/mL (yeast).

**Directions for this fork (high priority — several already scheduled as TODOs):**
- [ ] **Make direct non-fluorescent-control subtraction a first-class FP mode**, over
  ratiometric Clear-normalization. (Validates the deferred "FP dark correction" TODO.)
- [ ] **Guard Clear-channel saturation:** flag `valid=0` when Clear ≥ ~60000, mirroring the
  existing sensor-failure semantics. Today the ratiometric output silently goes nonlinear.
- [ ] **Enforce a minimum ex/em separation** in `chibio_fluorescence.recommend_fp_settings`
  to avoid the scatter peak (90° geometry). The Stokes-shift rule already leans this way.
- [ ] **Surface realistic sensitivity in the GUI:** warn when expected signal is likely
  sub-detectable and suggest a plate-reader pre-check.
- [ ] **Per-device fluorescence calibration constants** (a bead-based reference stored per
  reactor), justified exactly like the per-M0–M3 OD factors.

*Access note: WebFetch was 403-blocked; full text retrieved via curl with a browser UA at
the `.full.txt` endpoint. Figures not visually inspected — findings from text/legends/Methods.*

---

## Source 2 — Literature landscape (breadth scan)

Starting point: Google Scholar `"chi.bio"`
<https://scholar.google.com/scholar?hl=en&as_sdt=0%2C5&q=%22chi.bio%22>

Scholar lists hundreds of citing works; PubMed indexes almost none (the period breaks its
parser; most Chi.Bio work lands in bioRxiv/arXiv/PLoS/ACS). Breadth landscape below
(excludes the key papers covered in their own sections).

**Distinct works / groups (confidence noted):**
- **Denton, Murphy, Norton-Baker et al. 2024** (ACS Biochemistry) — pH control add-on for
  enzymatic PET hydrolysis; the closest thing to a published *hardware* fork. *High.*
- **Díaz-Iza, Arboleda-García, Boada, Vignoni et al. 2025** (Applied Sciences) —
  standardized OD/fluorescence calibration + online cell-specific growth & protein-synthesis
  rate estimation. *High.*
- **Vignoni/Boada group 2024** (IFAC-PapersOnLine) — mini-bioreactor part characterization
  of a genetic circuit; absorbance/fluorescence calibration, online growth-rate estimation. *High.*
- **Brancato, Salzano, De Lellis, di Bernardo 2024** (L4DC / arXiv 2312.09773) — in-vivo
  RL control of microbial population density in Chi.Bio. *High.*
- **Brancato, Salzano, Fiore, Russo, di Bernardo 2024** (IEEE L-CSS / bioRxiv 2024.03.08) —
  ratiometric control of two populations via a dual-chamber bioreactor. *High.*
- **Salzano/di Bernardo 2026** (arXiv 2511.08554) — model-based + sim-to-real learning
  control of a two-strain *E. coli* consortium composition. *High.*
- **di Bernardo group 2024** (ACS Synthetic Biology) — in-vivo multicellular feedback
  control in synthetic microbial consortia; Chi.Bio as the culture platform. *Medium-high.*

No solid Chi.Bio-specific hits for cyanobacteria/biofilm or classic ALE were found — treat
those domains as *absent/uncertain*, not confirmed.

**Application clusters:**
1. External/in-vivo feedback & learning control of populations (di Bernardo/Salzano) — the
   largest recurring cluster; Chi.Bio as an actuation+sensing testbed for control theory.
2. Synthetic-biology circuit/part characterization & growth-rate estimation (Vignoni/Boada).
3. Optogenetic feedback control of gene expression (the platform's headline use).
4. Continuous culture / turbidostat–chemostat growth control (generic backbone).
5. Hardware extension / bioprocess (pH-controlled reactors, Denton).

**Recurring praise:** cost 1–2 orders below commercial; all-in-one in-situ integration
(heating, stirring, pumps, spectrometry, multi-FP fluorescence, optogenetic/UV inputs);
open-source Python OS; up to 8 units/computer; tight OD control (~2%); robust online
growth-rate estimation; open expansion port.

**Recurring complaints/limitations:** OD-calibration bugs & fragility (chi.bio forum: OD0
handling, wrong conversions in older software); inducer **cross-contamination** in shared
tubing (protocols require flushing ~500 mL water between runs); small-culture-scale limits;
calibration/standardization gaps that *motivated* the Díaz-Iza and Vignoni calibration
papers. *Complaint set is medium-confidence — from forum + calibration papers, not a
systematic review.*

**Forks/extensions:** ReacSight (below); Denton pH mod; di Bernardo dual-chamber; and the
built-in external expansion port (power + digital interface) is the documented extension
mechanism. This repo is another (unpublished) fork.

---

## Source 3 — Steel et al. 2020, PLoS Biology (the reference paper)

**H. Steel, R. Habgood, C.L. Kelly, A. Papachristodoulou.** *"In situ characterisation and
manipulation of biological systems with Chi.Bio."* PLoS Biology 18(7):e3000794, 2020.
<https://doi.org/10.1371/journal.pbio.3000794> (PMID 32730242, PMC7419009)

The authoritative account of intended use. Full main text read; the S1 supplement (OD
calibration, laser/LED/spectral analysis, temp/OD regulation detail) was title-only, so a
few precise numbers live there.

**Designed capabilities:**
- **OD:** 650 nm laser, analogue feedback circuit for stable/temperature-insensitive reads,
  calibrated against a benchtop spectrophotometer. 12–25 mL working volume (runs at 20 mL),
  30 mL flat-bottom glass tubes, noncontact optics.
- **Continuous culture:** turbidostat + chemostat. Two of four pumps typically do
  turbidostat in/out; the other two free for inducer/media or reactor-to-reactor transfer.
- **Temperature:** medical-grade IR thermometer (noninvasive); PCB heat plate up to
  **2.0 °C/min**; cooling passive. Air thermometers monitor environment.
- **Pumping:** four peristaltic pumps, independent speed (up to **1 mL/s**) & direction,
  jointless 4.5 mm silicone tubing.
- **Optogenetics/light:** seven-colour LED (six visible + 6500 K white). Named wavelengths:
  457, 523/525, 595, 623/625 nm; independent PWM driver per LED → intensity over **three
  orders of magnitude**. Separate **280 nm UV LED** for stress/kill/mutagenesis.
- **Spectrometer/fluorescence:** eight optical filters + unfiltered "Clear"; per-channel
  gain & integration time; dark-photodiode baseline/temperature calibration **before every
  read**. Fluorescence reported **ratiometrically** (emission band ÷ total excitation).
- **Multiplexing:** one computer runs up to **8 reactor/pump pairs** over an internal I2C
  bus; Python OS + HTML/JS UI; CSV logging; user "custom program" Python framework.

**Validation / performance numbers:**
- Temperature accurate to **±0.2 °C near 37 °C** (air ±0.5 °C); tracked a setpoint path over
  5 h with minimal error/overshoot (PID + MPC).
- Turbidostat holds OD **within ~2%** of setpoint; can dither OD for growth-rate estimation
  at near-constant density.
- Growth-rate vs temperature (25→37 °C); UV dose response (cells adapt, recover).
- Optogenetics: CcaS-CcaR→GFP via red (623/625, off) / green (523/525, on). Open-loop is
  nonlinear; **closed-loop PI** steered fluorescence along a target profile *without a model*.
- Two orthogonal FPs (GFP+RFP) with negligible cross-talk; activation detectable **~20 min**
  after induction (fluorophore maturation).

**Limitations / calibration caveats:**
- **OD zero must be re-blanked per reactor per media type** with fresh media before each
  experiment (matches the `od-blanking` memory).
- Fluorescence uses a subtracted baseline (WT-no-plasmid) + 10-min moving-mean smooth; a
  small apparent GFP rise was actually aTc inducer autofluorescence — artefacts are real.
- Gain/integration fixed per measurement. GFP: 457 nm @0.1, ×512, 0.7 s, Clear base /
  550 nm emit. RFP: 595 nm @0.1, ×512, 0.7 s, Clear base / 670 nm emit.
- Open-loop optogenetic control is unreliable → feedback is needed.
- Predates the V1/V2 LED split in this fork; treat wavelength/LED assignments as
  version-dependent.

**Control philosophy:** a fixed **~60 s automation cycle** (stir off → settle → measure →
add/remove media → recompute inputs). Temp/OD use PID + MPC; optogenetic output uses PI
closed-loop updated each minute from measured fluorescence. **Core thesis: in-situ
closed-loop beats open-loop** because biology is nonlinear and model-dependent; feedback
removes the need for accurate a-priori models.

**Keep faithful to:** noncontact optics + ratiometric (excitation-normalized) fluorescence;
dark-photodiode calibration before every read; per-device/per-media OD blanking as
mandatory setup; analogue-feedback laser stability; per-LED PWM (3 orders); settle-before-
measure; the ±0.2 °C / ~2% OD fidelity targets; I2C serialization across up to 8 reactors.

---

## Source 4 — Steel et al. 2019, bioRxiv preprint (the device, implementation layer)

**Same authors.** *"Chi.Bio: An open-source automated experimental platform for biological
science research."* bioRxiv 796516, 2019. <https://doi.org/10.1101/796516>

Substantively the same as the 2020 version (same numbers, 60 s cycle, PID+MPC, ratiometric
fluorescence) — it's the *rationale* layer. The load-bearing engineering detail is in
Supplementary **Notes S1–S15**, which were **not** fetchable, so the main text names no
chips (no "BeagleBone", "AS7341", "Flask", or mux part number — those are repo facts, not
preprint facts).

**Extra implementation detail worth recording:**
- Three modular sub-units via micro-USB (~$300, reactor 11.5×5.3×5.3 cm); one computer
  drives up to 8 reactor/pump pairs; "multiplexed I²C bus" confirmed (mux part in S-notes).
- Stirring: off-the-shelf fan magnetic assembly + standard stir bars.
- Fluorescence procedure = S15; OD calibration = S5; temp control = S11; OD control = S12;
  compute board = S8; web UI = S9; custom-program framework = S10.
- **Concrete settings to preserve** (same as 2020): GFP 457 nm @0.1, ×512, 0.7 s, Clear
  base, 550 nm emit; RFP 595 nm @0.1, ×512, 0.7 s, Clear base, 670 nm emit. Optogenetics:
  green 525 / red 625 nm @0.1; graded induction = red fixed 0.1, green varied (Olson et
  al.). WT-no-plasmid baseline subtracted; 10-min moving-mean smoothing. Cells held at
  **OD 0.4** for FP/opto work; stir speed 0.6.

**If you want the mux addressing, OD calibration polynomial, or temp MPC model:** point a
follow-up at the supplement PDF (Notes S1–S15) — they weren't accessible here.

*Access note: bioRxiv 403-blocks WebFetch; main text retrieved via curl.*

---

## Source 5 — Bertaux et al. 2022, ReacSight (orchestration + reactive control)

**F. Bertaux, S. Sosa-Carrillo, V. Gross, A. Fraisse, C. Aditya, M. Furstenheim, G. Batt.**
*"Enhancing bioreactor arrays for automated measurements and reactive control with
ReacSight."* Nature Communications 13:3363, 2022.
<https://doi.org/10.1038/s41467-022-31033-9> (PMID 35690608, PMC9188569)

**What it is:** a hardware+software *strategy* to bolt sensitive plate-based measurement
onto low-cost bioreactor arrays and close reactive control loops. Gap filled: stock reactors
(eVOLVER, Chi.Bio) measure only in-situ OD + weak high-background fluorescence — no
gene-expression / cell-size / genotype-ratio data and no feedback from such data. A cheap
pipetting robot (Opentrons OT-2, native Python API) physically bridges reactor → measurement
device (benchtop cytometer or Tecan reader).

**How it uses Chi.Bio:** two interchangeable versions — a custom optogenetic array and an
array of **stock Chi.Bio reactors** (explicitly to show a lab with no bioreactor could
replicate it cheaply). Eight reactors feed one plate column/timepoint; cytometer column
washed to <0.2% carry-over; 192 samples → 24 unattended timepoints/reactor. **Interface is
HTTP over the local network:** every instrument's Python API is wrapped in a **Flask** app
and a single orchestrator drives the experiment via `requests` calls (+ Discord webhooks for
alerts). **Chi.Bio drops straight in because it is already a Flask/HTTP app.** They report
**no Chi.Bio-specific limitation** beyond the generic measurement-blindness of all such
reactors; the Chi.Bio version reproduced light inductions with "excellent reactor-to-reactor
reproducibility."

**Reactive control implemented:**
- Real-time optogenetic gene-expression control (EL222 blue-light): a 2-variable/3-parameter
  ODE (mRNA half-life 20 min, protein 1.46 h) drives **MPC** — SciPy bounded search
  optimizes the next 10 light duty cycles over a 5 h horizon. Accurate parallel setpoint
  tracking; quadruplicate reruns *months* later matched.
- Cytometry-gated competition assays (auto gating + spectral deconvolution).
- Two-strain consortium ratio control (OD setpoint used as an MPC steering knob; small
  steady-state error from media differences).

**Architecture lessons:** single orchestrator + Flask-wrapped per-instrument APIs + HTTP; a
generic object-oriented **event system** (`if <condition> then <action>`); **exhaustive
single-file logging** of every instrument operation; `pyautogui` "click-driving" for
GUI-only closed instruments lacking APIs.

**Directions for this fork:**
- [ ] Add ReacSight-style **POST hooks** so an external orchestrator can drive the device
  (Chi.Bio already speaks Flask/HTTP; the ReacSight repo interfaces to Chi.Bio directly).
- [ ] Add a generic **event abstraction (condition → action)** alongside the existing threads
  (`RegulateOD`, `Zigzag`) to make reactive control declarative, not hardcoded per loop.
- [ ] Adopt **single-file exhaustive operation logging** (every actuation) to complement CSV
  data logging.
- [ ] MPC opportunity: the AS7341 fluorescence + on-board optogenetics could host the same
  ODE-MPC light loop *locally*, without external cytometry.

*Access note: main-text architecture complete; deepest Chi.Bio pin/pump wiring is in the
Supplementary Note (not in the PMC feed) — see the ReacSight Git repo for integration code.*

---

## Source 6 — Joshi, Yong & Gyorgy 2022 (turbidostat characterization in practice)

**S.H.-N. Joshi, C. Yong, A. Gyorgy.** *"Inducible plasmid copy number control for synthetic
biology in commonly used E. coli strains."* Nature Communications 13:6691, 2022.
<https://doi.org/10.1038/s41467-022-34390-7> (PMC9637173). **Chi.Bio is used, in exactly
this fork's target mode.**

**Why automated culture:** TULIP is a self-contained plasmid whose copy number (PCN) is
tuned by Cuminic acid. Proving PCN can be *dynamically re-set and then held stable* over
~50 generations without runaway replication or growth cost is a multi-hour claim batch
flasks can't test cleanly — a turbidostat holds density fixed so expression and growth track
at constant physiology.

**Exactly how they used Chi.Bio:**
- Mode: **turbidostat**. Pre-assembled LabMaker units, Operating Software v2.3.
- 20 mL M9-Gluc + antibiotic/chamber; overnight culture diluted **1:200**; 37 °C.
- Target **OD600 = 0.5** (bounds 0.6 / 0.4); sampled every **1 min** for **48 h**.
- Readout: onboard **GFP (Ex 457/35, Em 510/40, gain 512×)** + OD600 as a *live monitor*,
  but every *quantitative* PCN datapoint came from **offline flow cytometry** on 20 µL grabs
  — **not** the AS7341.
- Dosing: **not via pumps.** Setpoint changes were made by **swapping the media reservoir**
  (different Cuminic acid) manually every **12 h**; the turbidostat washed the culture into
  the new steady state. PCN retuned in ~3–4 h (3–5 generations).
- Multi-reactor: parallel chambers across the induction range; 48 h / >50 generations.

**Limitations / workarounds:** they did **not trust onboard fluorescence for
quantification** (independently corroborating Source 1) — flow cytometry for every real
point. Dosing was manual reservoir swaps, not programmed pump ramps. Antibiotic selection
required (TULIP is progressively lost without it).

**Directions for this fork:**
- Reservoir-swap dosing sidesteps the pumps → programmed inducer gradients are a genuine
  capability gap worth exposing in the pump/turbidostat UI.
- GFP gain 512× is a usable reference, but validate the AS7341 against an external instrument
  before presenting it as quantitative.
- **OD 0.5 ± 0.1, 1-min cadence, 48 h** is a proven, gentle characterization envelope.

---

## Source 7 — Wenk et al. 2022/2024 (long adaptive-evolution run)

**S. Wenk, V. Rainaldi, K. Schann, H. He, M. Bouzon, V. Döring, S. Lindner, A. Bar-Even.**
Preprint: bioRxiv <https://doi.org/10.1101/2022.09.28.509898>. Published as *"Evolution-
assisted engineering of E. coli enables growth on formic acid at ambient CO₂ via the Serine
Threonine Cycle,"* Metabolic Engineering 88:14–24, 2024,
<https://doi.org/10.1016/j.ymben.2024.10.007>. **Chi.Bio is used.**

**Goal:** the Serine Threonine Cycle is a synthetic *autocatalytic* C1-assimilation route
letting *E. coli* grow on formate at ambient CO₂. Reached full formatotrophy by evolution.

**How Chi.Bio was used — two evolution stages:**
- **ALE1 (manual):** 14 mL tubes, serial batch dilution to OD 0.01 when OD>0.5; ~9 weeks.
  *Not* automated.
- **ALE2 (Chi.Bio):** **turbidostat**, auto-diluting at cuvette-equivalent OD600 **0.5** to
  keep cells exponential. HEPES minimal medium, starting **70 mM formate + 2 mM glycine**;
  glycine halved ~every 12 doublings to 0 while formate rose to **120 mM**. **Full
  formatotrophic growth ~day 90; total run ~150 days.** Number of parallel reactors,
  generation counts, and doubling times are in Fig 4B (not in text). Causal mutations found
  by resequencing: *thrA* S310P/S440P, a 39 bp thr-operon leader deletion, a *pntAB*
  promoter mutation (~13× transhydrogenase → NADPH supply).

**Disambiguation:** web search conflates this with a sister Bar-Even paper — Satanowski et
al., Nat Commun 2025, <https://doi.org/10.1038/s41467-025-57549-4> — which used the **GM3**
machine (190 days, ~750 generations), *not* Chi.Bio. Shared Genoscope co-authors make the
mix-up easy. This STC paper's automated arm is Chi.Bio.

**Directions for this fork:**
- **Selection pressure ≠ the dilution loop.** The turbidostat only held OD constant; the
  actual driver was a *scheduled medium-composition ramp* (glycine down, formate up) over
  months. A control stack for ALE wants **first-class staged/scheduled media recipes and
  pressure ramps**, not just a fixed setpoint. (Same gap as Source 6, from the other angle.)
- **Multi-month unattended runs (~150 days) are the norm** → OD-setpoint stability, blank
  drift, and un-crashable comms matter more than peak accuracy (aligns with the
  re-blank-after-restart and watchdog concerns).
- **Log densely enough to reverse-engineer later:** the payoff came from correlating a
  phenotype flip (~day 90) against timestamped OD/growth-rate logs + whole-genome sequencing.

---

## Source 8 — Pouzet et al. 2020 (optogenetics review; where Chi.Bio sits)

**S. Pouzet, A. Banderas, M. Le Bec, T. Lautier, G. Truan, P. Hersen.** *"The Promise of
Optogenetics for Bioproduction: Dynamic Control Strategies and Scale-Up Instruments."*
Bioengineering 7(4):151, 2020. <https://doi.org/10.3390/bioengineering7040151> (PMC7712799)

**Positioning:** instruments sorted into three tiers — mL-scale illumination plates (LPA,
24-well), **mini-bioreactors** (Chi.Bio + eVOLVER together, ≥30 mL, fluidics, multi-λ
illumination, OD, stirring, temp, ~16-unit arrays), and industrial photobioreactors.
Chi.Bio/eVOLVER niche: an intermediate scale-up step. **Chi.Bio's called-out strength:** its
7-colour LED + small spectrophotometer measure **≥2 fluorescence outputs**, which the
authors flag as crucial for fluorescent-biosensor-based real-time (cybergenetic) control.
**Limitation of both:** no pH and no dissolved-oxygen control (though implementable); too
small to reproduce large-volume growth/production → won't replace pilot-scale testing. Vs
photobioreactors, mini-scale *avoids* light-penetration problems (small + brightly lit).

**Dynamic light-control strategies (escalating):** (a) simple switch (flux rewiring,
growth/production decoupling); (b) **duty-cycle / pulsed modulation** for graded induction
strengths hard to get with switch inducers (Lalwani ~17-min cycles; Zhao periodic 30-min
pulses every 10 h tripled isobutanol); (c) **bidirectional** (OPTO-EXP/INVRT); (d)
**cybergenetics** — closed-loop feedback (optogenetic actuator + FP/growth-rate biosensor +
control algorithm), presented as the aspirational best practice. Induction timing relative to
growth phase matters (late exponential, ~OD 1).

**Light-delivery challenges:** penetration/attenuation in dense cultures (light-shading);
surface-to-volume ratio governs exposure; wavelength choice enables multiplexing several
optogenetic systems; heating/uniformity tied to stirring. Minor at mini-scale.

**Directions for this fork:**
- [ ] Expose **duty-cycle / pulse-train** LED control (period + fraction), not just on/off —
  graded induction is the whole advantage of light over switch inducers.
- [ ] Support **multi-wavelength combinations** and **inverted (dark-on)** programs.
- [ ] Close the loop: drive LEDs from live OD/fluorescence (the two-FP readout) — the exact
  biosensor role the review names Chi.Bio for.
- [ ] Gate induction on growth state (OD/growth-rate triggers); log per-cell expression to
  hold it constant as density changes.

---

## Source 9 — Forman 2020 (open-source control-systems primer)

**C.J. Forman.** *"Controlling control—A primer in open-source experimental control
systems."* PLoS Biology 18(9):e3000858, 2020.
<https://doi.org/10.1371/journal.pbio.3000858> (PMC7508385)

A short conceptual Primer commenting *on* the Chi.Bio paper — principle-level, not an
engineering manual. (Watchdogs, graceful failure, and calibration are barely touched.)

**Core principles:** the shift from expensive single-measurement instruments toward
affordable, reconfigurable *multiparameter* platforms built from cheap commodity chips.
Value is in flexibility and channel count, not per-channel fidelity: "each measurement may
not be as accurate... more than compensated for by enhanced understanding of the
interactions between parameters." Software is a first-class experimental component, ideally
embedding a model (digital twinning) comparing theoretical vs observed behaviour.

**Chi.Bio as anchor case:** praised as "a great example of an open-source multiparameter
control system." Contrasted with the author's APEX polymer-chemistry rig (~$20k, lab-grade
optics) — Chi.Bio ~$800, 8 reactors on one BeagleBone, a ~$9 AS7341-class spectrometer vs
APEX's $2k+ one. Arduino/RPi/BeagleBone all endorsed because bio/chem processes are slow.
eVOLVER not mentioned.

**Design vocabulary to design against (Box 1):** response time, sampling rate, bandwidth,
sensitivity, noise, processing gain. Sampling rate must exceed the fastest process of
interest; noise is beaten by summing/integrating measurements — but *control decisions have
a finite deadline*, so unbounded integration isn't available. I2C/SPI as the universal
primary-secondary bus. Only safety note: Chi.Bio's "watch circuit" that cuts power on
splash-induced short circuits. Data: historical accumulation is "extremely helpful but
creates memory/processing requirements."

**How this fork already matches the primer (don't "fix" these):**
- `runExperiment`'s 3× median+spread replication *is* the "sum to beat noise, but decide
  within a finite deadline" principle — keep replication bounded by the cycle deadline.
- The I2C single-chokepoint (`I2CCom` + global `lock`) is the endorsed primary-secondary bus
  model — architecturally sound, not a smell.
- `valid=0` / last-known-value semantics + the hardware-killing watchdog *exceed* the
  primer's advice (it only cites a splash short-circuit cutoff). Preserve them.
- The MPC heater model is exactly the "digital twinning" the primer values as the endgame.
- The $9-spectrometer tradeoff (channel count over optics fidelity) is validated — don't
  over-engineer the optics.
- **Validate the cycle period against loop bandwidth**, not just convenience: sampling rate
  must exceed the fastest controlled process (OD/turbidostat, thermostat).

---

## Synthesis — the directions, ranked

**Do first (multiple independent sources agree the platform actively misleads today):**
1. **Finish the fluorescence path.** Non-fluorescent-control subtraction as a first-class
   mode; Clear-saturation guard flag (≥~60000 → `valid=0`); minimum ex/em separation in the
   recommender; GUI sub-detectability warning; optional per-device bead calibration.
   *Sources 1 + 6 both independently distrust the onboard FP for quantification.*

**Do next (a real, repeatedly worked-around capability gap):**
2. **Scheduled media/inducer programs.** First-class staged recipes and inducer/pressure
   ramps in the turbidostat/pump UI, beyond a fixed OD setpoint. *Sources 6 (manual
   reservoir swaps) + 7 (months-long glycine/formate ramp).*

**Worth doing (leverage what the platform already is):**
3. **Optogenetic control depth:** duty-cycle/pulse-train LED programs, multi-λ combos,
   inverted programs, growth-state-gated induction, LEDs driven from live OD/FP. *Source 8;
   local MPC-of-light per Source 5.*
4. **Orchestration hooks:** ReacSight-style POST endpoints + a declarative event
   (condition→action) layer + exhaustive single-file operation logging. *Source 5.*

**Preserve (don't regress; the primer literally praises these):**
5. I2C chokepoint + global lock; bounded replication; watchdog + `valid=0` semantics;
   per-device OD calibration; MPC heater model; ~2% OD / ±0.2 °C fidelity targets;
   settle-before-measure; ratiometric-as-default *only until* the FP rework lands. *Sources
   3, 4, 9.*

**Open follow-ups / gaps in this review:**
- Steel supplement Notes S1–S15 (mux addressing, OD calibration polynomial, temp MPC model)
  and the ReacSight Supplementary Note (Chi.Bio pin/pump wiring) were not fetchable — point a
  follow-up at those PDFs if the exact values are needed.
- No confirmed Chi.Bio work in cyanobacteria/biofilm or classic ALE — treat as uncertain.
- The forum-sourced complaint set (OD-calibration fragility, tubing cross-contamination) is
  medium-confidence; a deeper Scholar crawl would firm it up.
