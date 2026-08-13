# Chi.Bio in the wild — how others use it, and what it means for this fork

A literature review focused on one question: **how do people actually use the Chi.Bio
bioreactor — effectively or not — and what should we change in this fork as a result?**

**Revision 2, 2026-08-11.** Revision 1 (2026-07-18) read nine sources. This revision is the
result of a systematic completeness audit across eight avenues run in parallel: a forward
citation crawl of both anchor papers, a preprint/thesis sweep, the code-repository and fork
network, the vendor documentation and community forum, deep reads of the works revision 1 only
named, the domains it declared absent, the supplements it failed to fetch, and an adversarial
fact-check of everything it asserted.

Result: **~40 works where Chi.Bio was actually used, modified, benchmarked or criticised**
(revision 1 had 9), plus the vendor forum read exhaustively, the Steel supplement recovered,
16 divergent software forks, and two published hardware forks. Every correction the audit found
to revision 1 is recorded in [§0](#0-corrections-to-revision-1) rather than silently edited.

**Revision 3, 2026-08-13** — a *depth* pass, not a breadth pass. The corpus search was re-run
from scratch (PubMed, Europe PMC exact-phrase, the fork network) and **came back complete: not
one new work**. What changed instead is that three of revision 2's "highest-value unread" items
have now been read in full, and they carry the most directly actionable numbers in the document.
Recorded in [§9](#9-revision-3--the-deep-read-2026-08-13), with the corrections it forced to
revision 2 kept there rather than silently edited.

This fork = a divergent refactor of `HarrisonSteel/ChiBio` (Flask app on a BeagleBone Black,
I2C bus, OD turbidostat, PI+MPC thermostat, peristaltic pumps, optogenetics via on-board LEDs,
AS7341 spectrometer for OD + fluorescence). Rig: **four** working reactors (M4 retired
2026-08-12, reported to LabMaker 2026-08-13), V2 LED board.

> **Implementing something, or planning an experiment?** Read
> **`docs/audit-2026-08-11-findings-and-actions.md`** instead — it is the work order derived from
> this review (verified defects with file:line, ranked actions with dependencies, and a bench
> briefing on operating envelopes, protocols and which readouts to trust). This document is the
> *evidence*; that one is what to *do*.

---

## TL;DR — the actionable conclusions

1. **The onboard fluorescence readout is not quantitatively trustworthy for dim FPs in cells.**
   Now supported by a metrology paper, five years of forum reports, three groups that built
   calibration layers on top of it, and — decisively — a *purpose-built* 90° fluorimeter with
   real interference filters that failed the same way. **The limitation is the geometry and the
   excitation leak, not the cheap spectrometer.** No gain, integration time or detector upgrade
   fixes it. Matched non-fluorescent-control subtraction is the route, and it is **the vendor's
   own lab protocol**, stated on the forum in Nov 2024.
2. **Scheduled dosing is the most corroborated gap in the entire review** — ahead of
   fluorescence. It now appears in **six papers (four from Steel's own lab)**, **six forum
   threads** all answered with "write a custom program with a modulo counter", and is named as a
   missing *capability category* by an outside benchmark. Chi.Bio does dilution-rate feedback
   only; seven peer platforms also do chemical composition.
3. **Raw OD is computed and thrown away.** Combined with a RAM-only blank, a mid-run restart
   silently changes the meaning of the OD column with no way to undo it. This is the highest
   value-per-line change available and revision 1 did not have it at all.
4. **The pump layer is the least trusted subsystem.** Four independent groups routed around it
   (manual pipetting, reservoir swaps, an external Ismatec pump, a syringe); three more complain
   about dosing resolution; and the `0.02` turbidostat clamp is a one-line software limit, not a
   hardware one. This fork also still carries two upstream pump bugs with published fixes.
5. **Long unattended runs are the norm** (7 d, 14 d, >200 h, 150 d) — but the *published*
   demonstration is 1.7 days, which is how an outside benchmark scored the platform. Comms
   robustness, blank persistence and dense logging matter more than peak per-read accuracy.
6. **Growth rate, not fluorescence, is what people actually trust and publish.** Six papers
   derive it from OD in four different ways; two of those estimators are open source.
7. **Chi.Bio being a Flask/HTTP app is a feature — but an undiscoverable one.** ReacSight built
   a whole orchestration framework on it; a major control group instead closed a 1-minute loop
   by **polling a CSV over SFTP**. That is a documentation failure, not a capability gap.
8. **The V1 seven-colour LED board is end-of-life.** Every new unit is V2, so this fork's
   V2/GFP caveat is permanent, not transitional.

---

## 0. Corrections to revision 1

An adversarial fact-check verified every citation, DOI, PMID/PMCID and load-bearing number in
revision 1 against primary text. **No hallucinated citations, no bad DOIs, no misattributed
primary papers.** The unusual `10.64898/…` bioRxiv prefix is genuine (openRxiv's post-2025
prefix). Load-bearing numbers — ±0.2 °C, ~2% OD, 2.0 °C/min, 1 mL/s, the 60 s cycle, the GFP/RFP
settings, Joshi's entire parameter set, Wenk's formate/glycine ramp, the Satanowski/GM3
disambiguation — verify against primary text, most of them verbatim.

The defects are a tier below fabrication. Three had propagated into `CLAUDE.md`/`TODO.md`.

| # | Claim in revision 1 | Correction |
|---|---|---|
| C1 | "flag `valid=0` when Clear ≥ ~60000" presented beside the Sambruna findings | **The paper never states 60000.** Its only number is the 65535 ceiling, and it samples nothing between 41000 and 65535. The guard is a defensible engineering choice — but its *support* comes from ams, not the paper: the AS7341's own AGC default drops gain at **87.5% of full scale = 57343**. See [§1.4](#14-the-as7341-itself). |
| C2 | Joshi et al. "did not trust onboard fluorescence" / "flow-cytometry cross-check" | **An inference the paper never makes.** They ran both simultaneously and never compared them. It is *revealed preference*, not corroborating measurement. Also their quantitative PCN came from **qPCR**; cytometry measured sfGFP. The genuine cross-checks are Sambruna (cells, pessimistic) and Díaz-Iza (dyes, optimistic). |
| C3 | "No solid hits for cyanobacteria/biofilm or classic ALE — treat as absent/uncertain" | **ALE is confirmed six times over**, including by Steel's own lab. Biofilm is a *headline application of Steel 2020 itself* (Fig. 3D, supplement S1O) which revision 1's own summary omitted. See [§6](#6-domain-verdicts). |
| C4 | "Preserve the fidelity targets (~2% OD, ±0.2 °C)" | ±0.2 °C is the **MLX90614's accuracy spec**, not a loop guarantee; the thermostat's performance is described only qualitatively. ~2% OD genuinely *is* a loop figure. Don't pair them. Forum reality: *"if it is regulating at 0.4 OD it should be something like 0.36 to 0.44"* — ±10%. |
| C5 | "protocols require flushing ~500 mL water between runs" attributed to the forum | The 500 mL figure **is real but is Steel 2020's Methods**, not the forum — it should be cited to the paper (which upgrades it to high confidence). The forum/manual protocol is 10 s of alcohol per tube. |
| C6 | Per-device FP calibration "justified exactly like the per-M0–M3 OD factors" | `CLAUDE.md` calls those `CF` constants inherited dead code. The recommendation is well supported; only the analogy is broken. The live in-repo precedent is `OD0['target']` via `CalibrateOD`. |
| C7 | "di Bernardo group 2024 (ACS Synthetic Biology) — Chi.Bio as the culture platform" | **Not Chi.Bio work at all**, and 2025 not 2024. Read in full: every experiment is shake-flask + flow cytometry. **Struck from the landscape.** |
| C8 | "Brancato et al. 2024 (IEEE L-CSS) — ratiometric control via a dual-chamber bioreactor" | **In silico only.** No dual-chamber rig was built for it; Chi.Bio supplied open-loop parameter-ID data from *one* reactor. The real hardware is the 2025 arXiv paper. |
| C9 | "Salzano/di Bernardo 2026 (arXiv 2511.08554)" | Posted **2025-11-11**, first author **Brancato**. |
| C10 | Items 2 and 3 listed as two groups (Díaz-Iza; "Vignoni/Boada group") | One research line, same first author; #3 is the conference precursor of #2. #2's author list omits corresponding author **Jesús Picó**. |
| C11 | Wenk's 39 bp thr-leader deletion credited to the Chi.Bio arm | It arose in **ALE1**, the manual tube arm. The paper separates them explicitly. |
| C12 | Sambruna "settings used: ex/em 395/510 and 523/620" | Those are the **bead** settings. **Cells were run at 457/510 on-device** — the number that matters for this fork's V2 LEDB caveat. (The paper is internally inconsistent here.) |
| C13 | "compute board = S8" | S8 is the **operating system** note. The control computer is S1B in the PLoS lettering. |
| C14 | "~16-unit arrays" ascribed to the Chi.Bio tier | Pouzet's figure attributes the 16-unit array to **eVOLVER**. Chi.Bio is capped at 8 per controller. |
| C15 | "cost 1–2 orders below commercial" | Unsourced. Forman's $800-vs-$20,000 is Chi.Bio vs a home-built research rig, not vs a commercial bioreactor. |
| C16 | "PubMed indexes almost none" | The papers *are* indexed; they are unfindable by the string `"Chi.Bio"` because the period breaks the query parser. Retrieval failure, not indexing failure. |

Two things the audit suspected and cleared: the **minimum ex/em separation rule IS supported**
by the paper (twice, qualitatively — *"Careful selection of the discrete excitation and emission
wavelengths … is necessary to avoid spectral overlap with the scattering peak"*), and no numeric
minimum was invented. And revision 1's claim that ReacSight interfaces to Chi.Bio directly is
**true from their repo** (not the paper) — they forked `app.py` and added routes, which makes the
POST-hooks recommendation *stronger*, though "drops straight in" is too clean.

---

## 1. The primary sources

### 1.1 Steel et al. 2020, PLoS Biology — the reference paper

**H. Steel, R. Habgood, C.L. Kelly, A. Papachristodoulou.** *"In situ characterisation and
manipulation of biological systems with Chi.Bio."* PLoS Biology 18(7):e3000794, 2020.
<https://doi.org/10.1371/journal.pbio.3000794> (PMID 32730242, PMC7419009). Preprint: bioRxiv
796516, <https://doi.org/10.1101/796516>.

**Designed capabilities.** 650 nm laser OD with analogue optical feedback, calibrated against a
benchtop spectrophotometer; 12–25 mL working volume (20 mL typical) in 30 mL flat-bottom glass
tubes, noncontact optics. Turbidostat + chemostat; two of four pumps typically do turbidostat,
the other two free for inducer/media or **reactor-to-reactor transfer**. Medical-grade IR
thermometer; PCB heat plate to **2.0 °C/min**; cooling passive. Four peristaltic pumps, up to
**1 mL/s**, jointless 4.5/2.5 mm silicone. Seven-colour LED (six visible + 6500 K white) at 457,
523/525, 595, 623/625 nm with per-LED PWM over **three orders of magnitude**; separate **280 nm
UV** LED. Eight optical filters + unfiltered Clear, per-channel gain and integration time, dark-
photodiode calibration **before every read**; fluorescence reported **ratiometrically** (emission
÷ base band). Up to **8 reactor/pump pairs** per computer over a multiplexed I²C bus.

**Validation.** Temperature accurate to ±0.2 °C near 37 °C *(sensor spec — see C4)*; turbidostat
holds OD within **~2%** of setpoint; OD dither for growth-rate estimation at near-constant
density; UV dose response; CcaS-CcaR→GFP optogenetics where **open loop is nonlinear and
closed-loop PI steered fluorescence along a target profile without a model**; two orthogonal FPs
with negligible cross-talk; activation detectable **~20 min** after induction.

**Applications revision 1 omitted:** biofilm monitoring is Application 1 (Fig. 3D + supplement
S1O) — see C3.

**Control philosophy.** A fixed **~60 s cycle**: stir off → settle → measure → add/remove media →
recompute inputs. **Core thesis: in-situ closed-loop beats open-loop**, because biology is
nonlinear and model-dependent, and feedback removes the need for accurate a-priori models.

### 1.2 The supplement (recovered) — the engineering values

The 2019 preprint's "Notes S1–S15" are published in PLoS as one 49-page **S1 Data**, lettered
S1A–S1S. Map: **S5 OD calibration → S1E** (pp. 11–15); **S8 → S1I** Operating System; **S9 → S1J**
User Interface; **S10 → S1K** Customisation; **S11 → S1L** Temperature; **S12 → S1M** OD control;
**S15 → S1P** Fluorescence. Compute computer is **S1B**.

**OD calibration.** `ODᵢ = log₁₀(OD₀/R)`, then a **quadratic with no constant term**, chosen "to
compensate for off-axis scattering events, which become significant at higher optical densities".
⚠ **The printed Eq. (S2) transposes its own coefficients.** The text prints
`OD = 1.374·ODᵢ² + 0.3974·ODᵢ`; Fig. S10c labels the fit `x = 0.397y² + 1.374y`. Checked against
the plotted curve: at ODᵢ=2 it crosses ≈4.3, which the figure form gives (4.34) and the text form
does not (6.29). **The figure is right.** This fork's `LASERa`/`LASERb` follow the figure's
structure, so the code is fine — but never cite Eq. (S2) as printed. Calibration standards were
**evaporated milk dilutions** against a GeneQuant 1300; Clear filter, gain ×1 laser / ×32 LED,
power 0.5/0.1. **`OD₀` must be calibrated per reactor** (device-to-device laser intensity varies).
RFPs at high concentration can absorb around 600 nm and **shift estimated OD by up to 10%**.

**Temperature "MPC"** is much simpler than the name implies: PI with a **gain switch at |e| = 2.0 °C**,
plus one feedforward term ∝ **P₁·(T_t − T_M)** where P₁ is media input rate and T_M is ambient —
purely to cover cold-media undershoot.

**OD control is a PII, not a PI.** P + two integrators, `G_I2 ≪ G_I1`, and **the second integrator
is zeroed whenever OD < OD_t**; its entire purpose is to cover a pump with *"temporarily reduced
suction"* from badly seated tubing. The outflow pump is always over-driven, so "most of the time
the output pump will be pumping air". Independently confirmed by a control group who benchmarked
against it. **Do not simplify that second integrator away** — it compensates a physical failure mode.

**Fluorescence (S1P) is more equivocal than the main text.** The published expansion of the
ratio is `Fluorescence = [S_E(OD) + f_cell(OD)]/S_B(OD) + f_FP(OD·FP)/S_B(OD)` — explicitly **not**
OD-independent, only *less bad* than `I_E/OD`. Quantified: during a growth run **I_E/I_B rises
≈1.35-fold while OD rises ≈4-fold**. Steel states the leak himself in 2020: *"we anticipate some
filter bleed-through from the excitation source to the emission band"*. The emission-band choice
is a published trade-off between bleed-through and signal, and **for GFP the answer is 550 nm,
not 510 nm** ("a significantly improved signal for larger measurement wavelength"). Published
figures apply a **20-min time-average plus a subtracted baseline**; the raw version shows a
baseline of ≈0.017 against a signal spanning 0.018–0.10 — i.e. **17–90% of the reading is
background**, in the paper's own data.

**Inter-device variability is mechanical.** S1G: *"Measurements of different LEDs with the same
spectrometer are more similar than measurements of the same LED with different spectrometers"*,
attributed to **component alignment and spectrometer aperture size**. That is why
Clear-normalisation partly fixes it, and why a per-device constant is the right *shape* of fix.

**Other constants worth having:** IR thermometer **MLX90614ESF-DCC**, ±0.2 °C only over 36–38 °C;
AS7341 filter peaks/FWHM 410/29 … 670/60; **gain ×1 for OD, ×512 for FP**; LED **LZ7** emitter,
PWM 200 Hz–1.5 kHz, *"generally each LED is run at 5∼10% of its maximal output"*, total optical
output to stay below 1.5 W; laser deliberately **de-focused** (>8° divergence) for detector noise;
heater 4×100 Ω ≈ 3 W; pumps **minimum pulse ≈0.2 s per minute**; mixing >95% complete within
**≈2.5 s**; *"the vast majority of noise in the OD measurement arises with the onset of stirring"*,
hence stir 40 s / settle 10 s / measure. I²C: lock → switch mux → transact → disconnect, **up to
≈500 Hz** — a prose description of exactly this fork's `I2CCom` chokepoint. **Mux part is not in
the supplement**; from the official BOM v1.3 it is a **TI TCA9548APWR**. The AS7341 is fixed at
**0x39**, so per-reactor addressing *must* go through the mux.

**S1O gives a free biofilm alarm:** as biofilm accumulates the required input pump rate → ∞, and
once the pump saturates **OD drifts above setpoint**. A rising pump rate at a stable OD setpoint
is a wall-growth signature computable from data already logged.

### 1.3 Sambruna, Tallarico & Cosentino Lagomarsino 2026 — the metrology paper

*"Calibration standards and sensitivity limits for fluorescence measurements with the Chi.Bio
open-source bioreactor platform."* bioRxiv, posted 2026-07-01.
<https://www.biorxiv.org/content/10.64898/2026.06.29.735387v1>

**Status as of 2026-08-11: still v1, unpublished, no code/data repository yet** (promised on
GitHub, future tense). Worth re-checking — their acquisition routines are the closest published
analogue to `chibio_fluorescence`.

Fluorescence microspheres (**Fluoresbrite YG Carboxylate**, Polysciences; **PS-FluoRed**,
microParticles; **AP-10-10**, Spherotech) plus PFA-fixed GFP *S. cerevisiae* (BY4741-RPL5-GFP) and
*E. coli* — **strain TB204**, a member of the same isogenic panel as this rig. Benchmarked against
a Tecan Infinite 200 PRO. Five reactors on one controller; **thermostat and pumps disabled**.

- **GFP falls below the detection limit.** Fixed GFP yeast indistinguishable from wild type
  (ratio ≈ unity); *E. coli* only marginal. The plate reader resolved both easily.
- **Root cause** (confirmed by H. Steel, pers. comm.): broad-spectrum LEDs leak excitation through
  the emission filters → a **concentration-dependent background**; the 90° geometry adds a scatter
  peak. Worse when ex/em are close.
- **The analytic model of the failure** (their Eq. 1) is the useful new part:
  `I_norm = (a·c + b)/(a_C·c + b_C)` — a ratio of two affine functions. It is linear in
  concentration only when `b/b_C ≈ a/a_C`; it flattens at high c and is background-dominated at
  low c. **Both asymptotes are artefacts.**
- **Inter-device variability** persists after normalisation (net signal / σ_device ≈ 3.3, "does
  not remain consistently above a reliable threshold"), and Fig. 5C shows *"non-trivial
  device-specific concentration trends that cannot be corrected by a simple additive offset"* —
  i.e. **a per-device scalar is not sufficient; the correction is concentration-dependent.**
- **Raising gain and LED power did not help.** Beads stayed cleanly separable on all devices →
  a sensitivity floor, not breakage.
- Settings: beads gain ×512 / power 0.1; **cells 457/510 on-device at power 0.01** (see C12).

**Their recommendations:** non-fluorescent media (LB is "massively autofluorescent");
**induce from a zero baseline** and subtract the pre-induction baseline rather than comparing two
steady states; **per-device calibration against a fluorescent reference standard**; verify the
expected signal on a sensitive instrument first. Hardware suggestion: a fibre-coupled dedicated
spectrometer with a high-pass filter.

**On this fork's 60000 guard.** The paper does not support it directly — but **Fig. S3 is more
damaging than the saturation argument**: with yellow-green beads, raw Clear **never exceeds
≈50000** and the normalised intensity **already plateaus from ~1×10⁷ particles/mL**. Per their
Eq. 1 that plateau is the `a/a_C` asymptote, not ADC saturation. **A guard keyed to the base count
alone catches one of two failure modes, and catches it late.**

### 1.4 The AS7341 itself

Datasheet DS000504 v3-00. Four findings bear directly on shipped code.

1. **Full scale is `(ATIME+1)×(ASTEP+1)`, capped at 65535** — so `== 65535` is a property of the
   *settings*, not the part. ASTEP resets to 999 and this fork never writes it. At the
   `ISteps=10` used by **LED V1/V2 auto-detection** (`app.py:257–270`), full scale is **11,000** —
   a value no saturation check in `chibio_optics.py` can recognise. If a bright board pins both
   `Baseline` and `NewLevel`, the `NewLevel > Baseline*3+20` test reads "LED absent" and **a V2
   board can be misdetected as V1**. Upstream's own comment at `chibio_optics.py:84` —
   *"Not sure if this saturation check above actually works correctly…"* — is this bug, noticed
   and never diagnosed. **Verified present in this fork.**
2. **The chip reports saturation in hardware, and the read is commented out** at
   `chibio_optics.py:72` (STATUS2, 0xA3). **`ASAT_ANALOG` fires before the digital counter fills**,
   so no count threshold — including `_FP_BASE_NEAR_SATURATION` — can ever see it. `ASTATUS`
   (0x94) returns the saturation flag *and* the gain actually applied, latched with the data, in
   one byte.
3. **ams' own threshold.** The spectral AGC's default `AGC_H = 3` drops gain at **87.5% of full
   scale = 57343**. The fork's 60000 is 91.6% — above ams' most aggressive default. The guard's
   existence is vindicated by the manufacturer; the number is marginally too permissive, and
   should be a *fraction of computed full scale*, not a bare constant.
4. **Gain steps are not powers of two.** 512× delivers **≈7.75×** the 64× response (±6%
   part-to-part), so `_gain_multiplier`'s `0.5·2ⁿ` carries ~7% systematic error across the range
   an auto-ranging EEM spans. And **channel centres run ~5 nm above Chi.Bio's labels**
   (ams typicals 415/445/480/515/555/590/630/680 vs 410/440/470/510/550/583/620/670), with
   `nm470`/`nm620` at the *edge* of tolerance — the Stokes-shift rule should carry ±10 nm.

Independent AS7341 literature is thin (11 PubMed records). The one multi-sensor comparison finds
its filters perform well, and a purpose-built **90° AS7341 fluorometer** achieves R² = 0.979 for
chlorophyll-a — but needed a Random Forest across channels, not a single-channel ratio.
**Consistent with the problem being Chi.Bio's optical architecture, not the chip.**

### 1.5 Forman 2020 — the open-source control-systems primer

*"Controlling control—A primer in open-source experimental control systems."* PLoS Biology
18(9):e3000858. <https://doi.org/10.1371/journal.pbio.3000858> (PMC7508385)

Principle-level commentary *on* the Chi.Bio paper. Value is in flexibility and channel count, not
per-channel fidelity: *"each measurement may not be as accurate… more than compensated for by
enhanced understanding of the interactions between parameters."* Chi.Bio praised as *"a great
example of an open-source multiparameter control system"*; ~$800 kit with a ~$9 spectrometer vs
the author's ~$20k APEX rig. Design vocabulary: response time, sampling rate, bandwidth,
sensitivity, noise, processing gain — **sampling rate must exceed the fastest process of
interest**, and noise is beaten by integrating measurements, but **control decisions have a finite
deadline**, so unbounded integration isn't available.

**How this fork already matches it (don't "fix" these):** `runExperiment`'s 3× median+spread
replication *is* "sum to beat noise within a finite deadline"; the I²C single-chokepoint is the
endorsed primary-secondary bus model; `valid=0` + the hardware-killing watchdog *exceed* the
primer's advice; the MPC heater model is the "digital twinning" it values.

---

## 2. How people actually use it — the application clusters

~28 works surviving triage from 113 enumerated citing works, plus preprints and theses. Only the
fork-relevant substance is recorded; confidence is stated where it is not "full text read".

### 2.1 Steel's own lab — the highest-authority usage, absent from revision 1

**Stacey, Sechkar, Corrao, Steel & Papachristodoulou 2026**, *"Quantitative Engineering and
Investigation of Synthetic Sponge RNAs in E. coli"*, bioRxiv
<https://doi.org/10.64898/2026.05.19.726096> — **the most complete published Chi.Bio operating
procedure in existence, from the source lab.** Turbidostat OD 0.5 **with dithering enabled as
standard practice**; stirring 0.5; vials autoclaved then ethanol-cleaned, tubing flushed with 70%
ethanol; **blank the OD after 15 min at temperature, then run a further 15 min purely to confirm
blank stability and re-blank if it drifted**. GFPmut3 457/510; mScarlet-I 523/583 or 595/670.
- **They do not trust raw ratiometric FP.** They adapted **FPCountR** to Chi.Bio: build an FP
  calibrant, sample the reactor around induction events, read those samples on a calibrated plate
  reader, and fit a **per-reactor linear model** converting processed Chi.Bio fluorescence →
  **molar intracellular concentration**. Background = **mean fluorescence in the 30 min before
  induction**, subtracted — independently the same "induce from zero" rule Sambruna recommends.
- **Cross-channel bleed-through is corrected explicitly**: GFPmut3 shows up in the mScarlet
  523/583 channel, so `mScarlet = Red − ratio × Green`. This fork has no bleed-through correction
  at all.
- Growth rate via **`GOFFREDOpy`** (<https://github.com/marco-corrao/GOFFREDOpy>), a Bayesian
  turbidostat filter: σ = 0.005, adaptivity 0.15, 1% outlier rejection, innovation-autocorrelation
  check. Fluorescence is **normalised by growth rate** to remove dilution artefacts.
- **Inducer step-changes are entirely manual** — disable OD control, empty the line, swap the
  bottle, wash pumps, spike 1 mL at `z = 21y − 20x`, reconnect. Induction timepoints "recorded or
  stored as metadata in the Chi.Bio GUI" — which validates this fork's events log.
- Complaints: a fluorescence spike *"due to turbidostat hardware issues"*; OD traces pre-processed
  by **"removing portions corresponding to known temporary hardware failures"**; first ~5 OD points
  after each inducer addition discarded.

**Corrao, Abrahams & Steel 2024**, bioRxiv <https://doi.org/10.1101/2024.04.08.588561> — **the
280/285 nm UV LED driven as a closed-loop selective pressure.** Three *E. coli* populations, each
with a differently tuned **PI controller holding growth rate at ≈1/3 of baseline** (~1.5 h⁻¹).
Two load-bearing design details: **the controller output is exponentiated**, because adaptation is
multiplicative in stressor level; and UV is reported as a fraction of maximum deliverable power,
so the experiment ends when the actuator saturates. **Adaptation went faster the better the
controller held setpoint** — controller tuning sets the rate of evolution. Theory says the optimal
inhibition setpoint is ~half the uninhibited growth rate. This is a **morbidostat in everything
but the actuator**, and this fork has both the UV LED and growth-rate estimation with no loop
connecting them.

**Lee, Morlock, Allan & Steel 2025**, *"Directing microbial co-culture composition using
cybernetic control"*, Cell Reports Methods 5:101009,
<https://doi.org/10.1016/j.crmeth.2025.101009> (PMC12049730) — **temperature as the control
actuator**, and the most inventive use of Chi.Bio's optics found anywhere.
- Composition sensed **label-free from a natural fluorophore**: *P. putida*'s **pyoverdine**, read
  at **395/440 nm**, chosen after a plate-reader EEM scan of both organisms — i.e. they did by
  hand exactly what `fluorescence_scan` + `recommend_fp_settings` automate. The *engineered*
  reporter (mKate2, PRNA1) was **too weak for Chi.Bio to see at all**.
- **Per-reactor fluorescence calibration built and shipped**: each reactor gets an identifier and
  a **characteristic offset + scaling factor** fitted against a dilution series of filter-sterilised
  supernatant, recorded "after stirring 5 s and settling 5 s, mimicking experimental conditions".
  They also verified temperature does not shift pyoverdine fluorescence in cell-free media.
- EKF + PI on temperature (species cross at **33.2 °C**), both **written into the Chi.Bio OS and
  run on the BeagleBone**. Held composition **7 days ≈ 250 generations**.
- Dither tightened to **0.455↔0.545**, explicitly *"to increase the frequency of dilutions, which
  improved the performance of the estimator"*.
- **Biofilm is a first-class failure mode**: *P. putida* wall growth escapes dilution and
  **artificially inflates apparent growth rate**; they switched to a ΔlapA strain.
- Fluidics they added: **0.22 µm filtered air vents on both the reactor lid and the media bottle**,
  a **one-way valve on the media inlet** against backflow, ethanol-sterilised daily.
- **Published artefacts:** a custom Chi.Bio OS fork on Zenodo (`10.5281/zenodo.14882854`), the
  composition estimator (`…14882858`), and 3D-printed lids (`…14887137`). The closest published
  sibling to this repo.

**Stacey, Lee, Gallup, Csibra, Papachristodoulou, Steel, Sechkar 2026**, *"Characterization of
Synthetic Gene Circuits with Absolute Quantification in Continuous Culture"*, Methods Mol Biol
**3041**:145–195, <https://doi.org/10.1007/978-1-0716-5304-3_8> — a **51-page protocol chapter**
whose case study is Chi.Bio, covering calibrant preparation, running the experiment, converting
to absolute units, and model parameterisation, with *"a full protocol and troubleshooting tips"*
for FPCountR-on-Chi.Bio. **Paywalled, abstract only. This is the single highest-value unread
document for the fluorescence rework** — obtain via institutional access before building. A
companion chapter (`…_13`, *"Dynamic Robust Control of Microbial Communities Using Cybergenetics"*)
is likewise paywalled.

**Allan, Zillig, Della Valle & Steel 2026** (PHA nanoparticles, bioRxiv
`10.64898/2026.03.17.712365`) — turbidostat co-culture at OD 0.3, composition steered by
**adding tetracycline by hand every 24 h**. A fourth Steel-lab paper whose dosing is a manual
daily human intervention.

### 2.2 Adaptive evolution and directed evolution — six confirmed works (overturns C3)

- **Wenk et al. 2022/2024** (Serine Threonine Cycle; Metab Eng 88:14–24,
  <https://doi.org/10.1016/j.ymben.2024.10.007>). ALE2 on Chi.Bio: turbidostat at
  cuvette-equivalent OD600 **0.5**, HEPES minimal medium, **70 mM formate + 2 mM glycine**,
  glycine halved every ~12 doublings to 0 while formate rose to **120 mM**; full formatotrophy
  ~day 90, **total run ~150 days**. **The selection pressure was the scheduled media ramp, not the
  dilution loop.** (Not to be confused with Satanowski et al. 2025, which used the **GM3** machine
  — 190 days, ~750 generations — and shares Genoscope co-authors.)
- **Klass … Keasling 2025** (Nat Chem Biol, PMC12303837) — MP6 hypermutator, turbidostat at
  **OD 0.75 for 7 days**, malonate as the growth-limiting selective agent; a parallel four-week
  manual serial-dilution arm. Chi.Bio replaced the fast arm.
- **Deng et al. 2025** (AEM, PMC12016552) — MutaT7 growth-coupled continuous directed evolution,
  17 mL, **OD 0.6 for 2 weeks**, ~1.7×10⁹ cells under mutagenesis at any instant. **Selective
  pressure was a manual temperature ramp, 37 °C → 27 °C.**
- **Ruehmkorff … Hochrein 2025** (NAR, PMC12448870) — ***S. cerevisiae***, turbidostat in **dither
  mode**, grow to 0.6 → dilute to 0.3, **each dither cycle defined as one generation**, >100
  generations over >200 h. The only work using dither as a **generation counter**.
- **Pentz et al. 2024** (LANL, bioRxiv `10.1101/2024.11.20.624476`) — ~100 generations on acetate
  as sole carbon source. *(Abstract + companion protocol only; bioRxiv 500s persistently.)*
- **Sitompul, Price, Tee & Wong 2023/2024** (Biotechnol J `10.1002/biot.202300577`) —
  *C. necator* H16, and **not a turbidostat**: 15 mL in a 30 mL vial, the fluidics unused, Chi.Bio
  serving as the logged **selection stage** of manual serial-transfer ALE, each cycle ending at
  *"early stationary phase"*.
- **Guyot et al. 2026** (CSBJ, PMC13199644) — library selection under **kanamycin at 120% of
  MIC₅₀**, OD 0.4 for 21–29 h.

**But the morbidostat proper is still not implemented** — a forum request opened June 2020 and
re-asked **April 2026**, unanswered. Steel's recommended design (2020) is **two reservoirs, mixing
the inflow ratio**, explicitly to avoid dispensing small precise volumes. Pioreactor ships
`PID Morbidostat` as a stock automation.

### 2.3 Consortia and ecology — arguably the largest cluster

- **Brancato, Salzano, De Lellis, Fiore, Russo & di Bernardo 2024** (L4DC, PMLR 242:941–953;
  arXiv 2312.09773) — sim-to-real DQN turbidostat control benchmarked against **Chi.Bio's own PI
  and a bespoke MPC**. All three comparable; the DQN does not lose to the stock PI, and at the
  lowest setpoint the PI and MPC both degrade ~2× while the DQN does not. Model fitted from a
  *single* open-loop run at a deliberately poor **6% MSE** — the point being that suffices.
  Cadence is 1 min, *"the sampling time imposed by the constraints of the bioreactor"*; dilution
  clamped to **[0, 0.02] mL/s**.
- **Brancato et al. 2025** (arXiv 2511.08554) — **the dual-chamber rig, built**: two Chi.Bio
  reactors physically interconnected, OD-only aggregate measurement at 1 min, an **EKF** to
  reconstruct the two populations (tuned by GA; EKF-vs-cytometry MSE 0.001/0.004), settling under
  an hour. ⭐ **The single most fork-relevant sentence in the corpus:** *"the two machines share a
  CSV file through an SFTP communication protocol"* — a leading control group closing a real-time
  loop by polling a file, on a device that is already a Flask HTTP server on the LAN. Their stated
  limitations are all software-addressable: aggregate-OD-only forced the EKF, and they write that
  in-situ fluorescence *"would eliminate the need for observers"*; and **peristaltic backflow
  "reduce[s] control input resolution at low actuation levels"**.
- **Lee, Morlock, Allan & Steel 2025** — see §2.1.
- **Ulrich & Mitri 2026** (bioRxiv `10.64898/2026.04.23.720424`) and **Sulheim, Teixeira, Ulrich …
  Mitri 2026** (`10.64898/2026.04.20.719729`) — **criticism by amputation.** A *"modified version
  of the Chi.Bio platform"* that **keeps only the laser OD sensor**: pumps replaced by an external
  Ismatec IPC, working volume set mechanically by an **overflow tube height**, aeration added by
  aquarium pump, vials sealed with **20 mm septa** and sampled by syringe. Explicit two-point
  calibration `OD₆₀₀ = k·log₁₀(R) + b`. The second paper publishes a full BOM: **Fisher 11593532**
  30 mL vial (used by three independent groups — a de facto standard), PTFE ID 1/16″ lines, and
  **silicone pump tubing bore 2.5 mm / wall 1 mm (Altec 01-93-1416/20)** — independently confirming
  the spec in this repo's `tubing-eu-sourcing` memory.

### 2.4 Circuit characterisation and absolute quantification

- **Díaz-Iza, Arboleda-García, Boada, Vignoni & Picó 2025**, Appl. Sci. **15(13):7442**,
  <https://doi.org/10.3390/app15137442>. Code: <https://github.com/sb2cl/MDPI2025-Calibration_Chibio>.
  **The concrete units answer.**
  - **OD → particles.** Blank with **PBS**; serial dilutions in the standard 30 mL vials read on
    both Chi.Bio (650 nm) and a Cytation 3 (600 nm); fit a **Hill/sigmoid**, not a line:
    `OD = a·xⁿ/(xⁿ+kⁿ)` with `x = ln(blank/raw)` — deliberately to model detector saturation.
    Then `Particles = 10^(p0+2)·(0.55·OD)^p1`, with p0/p1 from a **silica-bead** series measured
    **once**, on the plate reader (beads are expensive → never used in the reactor).
  - **Fluorescence → MEFL.** **Fluorescein sodium salt**, 1:2 dilutions from 21.17 µM, Chi.Bio at
    **ex 457/35, em 550/42**. Two-step: raw → NFR by dividing by the **molecular brightness of the
    fluorophore actually present** (**597.5 for fluorescein during calibration, B_GFP when
    measuring cells** — an easy silent error worth encoding in the UI), then NFR → MEFL by dual
    exponential. Report **MEFL·particle⁻¹**. R² 0.999.
  - **An automated on-device calibration wizard**: pumps dilute *continuously* to a preset
    **sensor-value marker** — not a target volume, explicitly because of *"the limited accuracy of
    the pumps when handling small liquid volumes"* — 4 reads averaged per point, reference typed
    into a custom UI page, then re-fit in place.
  - On-device **super-twisting sliding-mode observer** (log-domain surface, EMA rescaling λ=0.5,
    scipy BDF) for µ and protein synthesis rate; **~1.5 h transient** before convergence.
  - **Two caveats:** they never test the sensitivity floor Sambruna documents (their GFPmut3 is
    constitutive and bright), and **they abandon ratiometric emit÷Clear entirely**, calibrating
    the raw emitter channel — a third position on FP normalisation, distinct from both upstream
    and Sambruna. Also their **OD blank is hard-coded**; this fork's per-reactor `CalibrateOD` is
    better on that axis — don't regress it while borrowing the model.
  - Bonus: their repo is an **independent modular refactor of the same upstream monolith**, with
    essentially the same seams this fork cut (I²C chokepoint, per-sensor/per-actuator modules,
    watchdog) — corroboration that the module boundaries are the natural ones. They also hit the
    gunicorn worker-timeout problem and moved to **WebSockets** pinned to one worker.
  - Precursor: Díaz-Iza et al., IFAC-PapersOnLine **58(23):97–102** (2024) — growth-rate-only,
    superseded; abstract-only (ScienceDirect blocks retrieval), no loss.
- **Joshi, Yong & Gyorgy 2022** (Nat Commun 13:6691, PMC9637173) — turbidostat, LabMaker units,
  Operating Software v2.3, 20 mL M9-Gluc, 1:200 overnight dilution, 37 °C, **OD600 0.5
  (bounds 0.6/0.4), sampled every 1 min for 48 h**, >50 generations. Onboard **GFP Ex 457/35,
  Em 510/40, gain 512×** as a live monitor; quantitative sfGFP from **offline flow cytometry**,
  PCN from **qPCR** (see C2). **Dosing by manual reservoir swap every 12 h**; PCN retuned in ~3–4 h.
- **Deng, Maurais, Etheridge et al. 2025** (J Biol Eng, PMC11951768) — Chi.Bio *"to ensure cultures
  achieve true steady states during the log phase"*, OD 0.5 (0.3 for the iFFL circuit).

### 2.5 Optogenetics — and a calibration gap nobody had noticed

- **Bertaux, Sosa-Carrillo, Gross, Fraisse, Aditya, Furstenheim & Batt 2022 (ReacSight)**,
  Nat Commun 13:3363, <https://doi.org/10.1038/s41467-022-31033-9> (PMC9188569). A pipetting
  robot bridges reactor → cytometer/plate reader; every instrument's Python API is wrapped in a
  **Flask** app and one orchestrator drives everything with `requests`. Eight stock Chi.Bio
  reactors; 192 samples → 24 unattended timepoints/reactor; <0.2% cytometer carry-over. Real-time
  optogenetic **MPC**: a 2-variable ODE (mRNA half-life 20 min, protein 1.46 h) with a SciPy
  bounded search over the next **10 duty cycles across a 5 h horizon**; quadruplicate reruns
  *months* later matched. Architecture lessons: single orchestrator, a generic **condition → action
  event system**, **exhaustive single-file logging**.
  **From their code** (`gitlab.inria.fr/InBio/Public/reacsight`, a fork of Chi.Bio's `app.py`):
  they **read OD through the 670 nm filter instead of Clear, specifically to stop optogenetic blue
  light contaminating the OD read**; they use a **per-reactor cubic with a constant term**; and
  their fluorescence read is **raw nm510 counts with no base normalisation at all**. Their
  turbidostat is a **bang-bang `if od > target: dilute` in a notebook** — they never used Chi.Bio's
  PII. Protocol is plain **GET** with `|`-separated batch commands. Dead volume ~2 mL; a **flood
  interlock** opens the drain 1.5× the input duration, started first.
  On the forum, François Bertaux states what the paper does not: *"the signal is low, so raw
  numbers cannot be compared between reactors. Also the OD matters a lot, even a small 'dither'
  will be visible on the reading."*
- **Lazar … Tabor 2025** (Nat Commun, PMC12852798) — **Chi.Bio LED intensity is uncalibrated
  arbitrary units.** To hit their optimum of 7 µmol m⁻² s⁻¹ green (established on an LPA) they ran
  a whole cross-calibration; the finding is that **the lowest testable Chi.Bio intensity,
  0.003 a.u., already matched the LPA optimum**, and *every* higher intensity reduced expression
  through phototoxicity. They also patched `app.py` for dynamic light programs. **A control
  spanning three orders of magnitude whose useful region sits at the very bottom needs a
  log-scaled input and a phototoxicity note, not a linear slider.**
- **González … Avalos 2025** (bioRxiv `10.1101/2025.03.04.641524`) — yeast, batch, a **manual
  10 s on / 100 s off duty cycle** at 457 nm; another hand-rolled ChiBio-AU → OD600 regression.
- **Saeed, Lewis, Fujiwara et al. 2026** (bioRxiv `10.64898/2026.06.29.735265`) — *C. necator* on
  formate with AI-designed rhodopsins. The load-bearing line: *"The APR wavelength was chosen
  **from the available Chi.Bio LEDs** as the shortest wavelength that supported stable assay
  operation **without measurable chromophore photobleaching**."* Photobleaching was managed by
  **scheduling darkness** (8 h dark → light → 4 h dark). Two implications: the discrete LED palette
  is a hard experimental constraint the UI should make legible (true centre wavelengths; V2's
  missing ~488 nm), and scheduled light is being hand-run today.
- **Pouzet et al. 2020** (Bioengineering 7(4):151, PMC7712799) — the optogenetics review that
  places Chi.Bio + eVOLVER in the mini-bioreactor tier. Chi.Bio's called-out strength is **≥2
  fluorescence outputs** for biosensor-based cybergenetic control; the limitation of both is **no
  pH and no dissolved-oxygen control**. Escalating strategies: simple switch → **duty-cycle/pulsed
  modulation** (Lalwani ~17-min cycles; Zhao 30-min pulses every 10 h **tripled isobutanol**) →
  bidirectional → cybergenetics.

### 2.6 Quantitative physiology, and the pump-throughput complaint

- **Droghetti … Cosentino Lagomarsino 2025** (Nat Commun, PMC11954927) — same lab as the metrology
  paper. *"While the ChiBio provides pumps to regulate OD, **the pumping rate was not fast enough**
  for the significant volume necessary for the dilution. Instead, a manual dilution was chosen,
  using a 10 mL pipette."* They also **cap usable OD at 0.8** and discard anything above as
  near-saturation. Their analysis recipe is worth copying: sliding-window average **on log(OD)**,
  dilution-stitching by a measured ratio, central-difference growth rate.
- **Olivi et al. 2024/2025** (NAR PMC11109954; Nat Commun PMC12371093) — turbidostat as a
  balanced-growth generator for single-molecule microscopy. Two things: a **Chi.Bio-AU → OD600
  ratio of roughly 2:1**, and *"A 650 nm laser diode was used… **instead of visible light, to
  prevent accidental photoactivation of PAmCherry2.1** due to the large emission spectrum of the
  LED"* — the first source flagging the **measurement light source as a photobiological
  perturbation**. Growth rate computed as **pumped volume ÷ vessel volume** — a free, OD-independent
  cross-check.
- **Koehler, Pentz … Hanschen 2025** (STAR Protocols, PMC12509892) — LANL's **`chemostat_regression`
  R package** (<https://github.com/lanl/chemostat_regression>), explicitly built to consume
  **Chi.Bio dither-mode CSV**: time, OD, fresh-pump rate, waste-pump rate. Binarises the pump rate
  to detect dilution cycles, then regresses ln-OD per cycle. **An external consumer of this fork's
  CSV schema, in R + ggplot2 — the maintainer's own stack.** Its stated limitations are complaints
  about the data these devices emit: cycle detection fails when **pump-rate values do not fluctuate
  in a consistent 0/>0 pattern**, and **>200,000 rows must be chunked**.
- **Deng, Beahm et al. 2026** (bioRxiv `10.64898/2026.01.30.702957`) — Chi.Bio purely as a
  **pre-conditioning** instrument: hold exponential phase at OD 0.6 for ~12 h, then hand off.

### 2.7 Batch use — a third of the corpus never touches the pumps

Six works run plain batch: Lazar's optogenetics, González's yeast, Sitompul's ALE selection,
Saeed's 50 h rhodopsin assays, Deng's 12 h pre-conditioning, and **Gallardo-Camarena et al. 2025**
(AMB Express, PMC12144029) — parallel **media screening** (LB/TB/PDB/KTM), 18 h, stir 0.8, no pH
control, before scale-up to a 3 L Applikon. **Turbidostat is not the only story, and
blank-then-regulate assumptions should not make batch awkward.** Two of these end a run on a
*condition* ("early stationary phase"; "8 h dark then light") that the software could detect.

### 2.8 Published hardware forks

- **Denton, Murphy, Norton-Baker, Lua, Steel & Beckham 2024**, *Biochemistry* **63(13):1599–1607**,
  <https://doi.org/10.1021/acs.biochem.4c00149> (PMC11223484). Code + CAD:
  <https://github.com/beckham-lab/Chi.Bio.pH> (GPL-3.0). **Harrison Steel is a co-author** — this
  is effectively a sanctioned fork and the best worked example of how the maintainer expects the
  platform to be extended.
  - Parts: ThermoScientific Orion #911600 probe + **Atlas Scientific EZO-pH** on an isolated
    carrier, through a **custom 3D-printed head plate**, titrant via **the stock pump board**,
    connected via **the stock expansion header** (SDA4/SCL5 — *"any I²C device can be implemented
    over this interface"*).
  - **The 3.3 V rail is the scaling limit, not the bus**: ~3 EZOs at once → external supply,
    staggered reads.
  - Software follows this fork's documented conventions exactly (state in `sysData`, threads on
    the `threadCount` pattern, reads through `I2CCom`). They feed the **IR thermometer into the
    probe's temperature compensation on every read**. Controller is **bang-bang with a dead zone**,
    30 s reads / 90 s control cycle, one fixed pump pulse per correction, plus a **max-volume
    overflow cap**, a running `voladded` accumulator, and a **"test flow rate" button** that fires
    one pulse so the user can weigh it.
  - **Bug in the published code:** `pHControlPumpFlag` is assigned in `pHControlPump()` without a
    `global` declaration, so the "block other I²C traffic during a pump pulse" guard in `I2CCom`
    is dead code. *(A good argument for this fork's convention of routing state through `sysData`
    rather than module globals — and a reason not to copy the pattern blind.)*
  - Results: conversion **92.6 ± 1.67%** vs an Applikon 1 L's **95.5 ± 2.02%**, with **20× less
    enzyme** — but pH held ±0.1 only **78.7/80.2%** of 72 h vs 95.8/98.6% at ±0.05. Their binding
    constraint: **fixed pulse volume 30–45 ± 10 µL, varying per pump and per titrant.** They also
    flag the **60 s stirring pause as a process artefact**, not just a measurement one.
- **Schoenmakers, Rad, Ihl et al. 2025** (iScience, PMC12341536) — Chi.Bio extended into a
  **bioelectrochemical reactor**: a 1 cm hole through the lid sealed with a septum, a zero-gap PEM
  electrolyser generating H₂ in situ, mass-flow-controlled CO₂, quadrupole MS on the exhaust.
  Runs ≥200 h, OD to 3.8. Second published fork to bolt an external sensor/actuator loop onto a
  device with no first-class expansion API.

### 2.9 Theses — the candid failure accounts

- **Jessen 2023** (QUT PhD, <https://doi.org/10.5204/thesis.eprints.237756>) — six reactors,
  riboswitch competition, OD650 target 0.5. Two failures reported plainly: *"After 5 hours the
  peristaltic pumps failed"*, and — the important one — **the onboard GFP readout was flat while
  the turbidostat was working**: *"fluorescence measurements exhibited only minor differences for
  induced vs uninduced riboswitches during the steady state. After 5 hours the peristaltic pumps
  failed, and a distinct fluorescence shift could be seen."* **That localises the ratiometric
  failure to precisely the mode this rig runs in** — with OD pinned constant, the emit÷Clear ratio
  carried essentially no induction signal, and separation appeared only once density began
  climbing. That is the signature of a readout dominated by concentration-dependent background.
- **Jandová 2026** (Brno UT MSc, <https://hdl.handle.net/11012/256668>) — thermophiles at **50 °C**
  for 72 h, benchmarked against a Biosan RTS-1 and an Infors Multifors. Three findings: **active
  aeration was actively harmful** (passive membrane aeration won); **stir-bar geometry is a
  first-order variable** — cylindrical vs tablet bar gave biomass 2.950 vs 0.505 g/L, a ~6×
  difference attributed to shear; and two nominally identical reactors under identical conditions
  differed by **~57% in product**. End-of-run **OD ≈ 7.5**, far outside the blanked range, reported
  without warning.
- **Orr et al. 2025/2026** (EcoEvoRxiv `10.32942/x2f948`; PLoS Biol 2026) — the only sizeable
  **chemostat** use found: 8 reactors × 5 replicates = **40 reactor-runs** at six fixed dilution
  rates, 1-min OD, 4 days with only days 3–4 treated as equilibrium *"due to the increased risk of
  evolutionary change"*. **One reactor dropped because its pump failed.** Every other group runs
  turbidostat; a first-class fixed-dilution-rate mode is under-served.
- **Barajas et al. 2026** (AAAI Symposium, JHU APL, <https://doi.org/10.1609/aaaiss.v8i1.42512>) —
  a **16-reactor Chi.Bio-derived array**. The architecture is the point: they **kept the
  8-reactors-per-controller boundary and federated over REST/HTTP**, with Kalman estimation and
  qLogEI Bayesian optimisation running remotely. That independently validates this fork's
  `single-owner rule` memory: the answer to scaling is a second controller plus an external
  orchestrator, not more threads.

---

## 3. Grey literature — the vendor docs and the forum

**The forum exists, is fully readable without login, and is a de-facto official channel.**
<https://chi.bio/forums/> — **189 topics / 846 posts, 2019-08 → 2026-07, with Harrison Steel
replying in 183 of 189 topics (97%)**. Enumerated from the site's own sitemap and read in full, so
this supersedes revision 1's "medium confidence" caveat entirely (see C5).

**There is no changelog anywhere on the site**, no Slack/Discord/mailing list, no wiki, no videos
or teaching materials. The current Software Setup Guide is **V2.3 (2022-04)**; the OS image is
frozen at **2021-06-18**; the repo has no tags and no releases. The Operation Manual is revised
**in place** — the 2022 and 2025 PDFs are both labelled "V1.2" and differ only by a check-valve
recommendation. **You cannot trust the version string.**

### 3.1 Recurring problems, ranked by topic count

| Theme | Topics | Verdict |
|---|---|---|
| Pumps / tubing / flow rate | 34 | **#1.** Poor pump-head seal; wanting slower rates. |
| I²C / multiplexer / comms crashes | 26 | **#2.** Nearly always moisture on the sense tracks. |
| OD measurement & calibration | 21 | Alignment/tube geometry dominates; real bugs are rare. |
| Fluorescence / FP | 16 | A consistent "I can't see my FP" pattern since 2021. |
| Custom programs / extension | 15 | Documentation gap, repeatedly acknowledged. |

**The single most-repeated official answer on the whole forum** is to wipe the **moisture-sensing
tracks** with alcohol. Root-caused to *"a change in 3d printing technology used to manufacture the
lids"*; fix is a **15/18 mm FKM O-ring**. And *"if you are having issues with crashing then 95%
probability the issue is the seal of the lid onto the glass for the vial."* GitHub issue #16 adds
the mechanical detail: **the top liquid-level sensing ring is *"at least 80% of the time the
offender"*** for "Failed to recover multiplexer", is trigger-happy with humidity, and is
**physically disconnectable**. **Lid sealing is a software-reliability issue on this machine.**

### 3.2 Fluorescence — five years of user reports

Sixteen topics, the same pattern every time: *the plate reader sees it, Chi.Bio does not*.

- **The canonical case** (May 2021, Caltech): sfGFP + mRFP1 at OD 0.5 using the paper's exact
  settings — *"across all three conditions (blank M9, GFP cells, and RFP cells), the Emit readings
  are essentially identical"*. The **baseband did move** (9000 → 20000); only the ratio was dead.
- **Steel names the mechanism plainly**: *"The real problem is filter bleed-through i.e. the amount
  of excitation light that makes it through the emission filter."* Recommended alternative: an
  off-the-shelf Ocean Optics spectrometer.
- **A quotable detection floor**: *"If it is <0.5% of 'very bright' it will be difficult to
  measure due to other autofluorescence and filter bleed-through."*
- **Media matters more than gain**: *"if you use LB you will get generally a TERRIBLE signal…
  I would strongly recommend using M9 media at least."*
- **The official normalisation caveat**: ratiometric *"reduces (by say ~90%) the influence of OD
  but it is not perfect"*.
- **⭐ THE VENDOR'S OWN LAB ALREADY DOES MATCHED-CONTROL SUBTRACTION**, stated Nov 2024 and
  **absent from the manual**: *"GENERALLY in our lab what we do is measure a 'zero' signal for
  each reactor… putting the same non-fluorescent sample in each (i.e. just cells + media), do the
  measurement, record the value as the 'zero' value. Then, we subtract that zero from the
  experimental data to bring them to a common baseline. Doing this we find we can get very
  reproducible results."* **Direction #1 of this review is the manufacturer's protocol**, 18 months
  before the metrology preprint reached the same conclusion.
- Also: how to recover the un-normalised number (multiply Emit by the baseband); Steel's lab uses
  **GFP 450→550 and mScarlet 595→670**, noting 620 brings *"a lot of GFP bleed-through"*; and
  long-Stokes-shift FPs are explicitly recommended — a **vendor endorsement of the rule
  `recommend_fp_settings` already implements**.

### 3.3 Capability gaps users work around

- **Scheduled dosing does not exist.** Six independent threads, all answered with *"add a
  conditional statement in the main loop (`runExperiment`) which turns the pumps on every
  12*60=720 cycles."*
- **No experiment end-time, no error log to file**: *"We do not at present log these anywhere
  other than the PuTTy window."*
- **No simulation mode.** Asked twice (2020, 2022); Steel's answer was *"a group at Imperial…
  decided that it was easier to just get a second beaglebone/chi.bio reactor and have that sitting
  on a bench as a test dummy."* **This fork's `CHIBIO_SIM=1` is the only working answer in the
  public record.**
- **Documentation is the acknowledged weak point.** Still open as of **2026-04-13**: *"apologies
  for the lack of documentation thus far; I need to work on a readme for the Github!… ideally as a
  precursor to a more fully-fledged API."*
- **HTTP is the officially blessed integration route**: *"send HTTP requests to the Chi.Bio server
  that runs on the control computer"*, repeated in four threads. The **expansion header** is the
  documented hardware extension point.

### 3.4 Operational numbers worth having

| Fact | Note |
|---|---|
| **The accurate OD blank procedure is buried in Troubleshooting**, not §3.2 | Blank in situ, at temperature, stirring stopped, then pipette cells in through the lid: *"This will typically reduce variability by more than 50%."* |
| Realistic OD regulation | *"if it is regulating at 0.4 OD it should be something like 0.36 to 0.44"* — ±10%, not ~2% |
| Tubing tolerance | *"if you depart from this by about more than 0.1mm"* pumps jam or fail to seal; replacements must keep **2 mm total wall thickness** |
| Pump-to-pump variability | *"we do not have an approximate calibration"*; *"might vary by up to 50% between pump heads"* |
| The turbidostat clamp | `if(Pump1>0.02): Pump1=0.02` — *"You could increase that."* |
| Back-siphon | A poor pump seal lets liquid retract and **contaminates the fresh-media bottle**; fix is tape or a McMaster 7757K41 check valve |
| Minimum working volume | **~15 mL**, set by the optical path |
| Growth-rate estimator | EWMA, learning rate **0.05** |
| Thermostat gains | `Gain=2.5`, `I += 0.0005·dt·e`; halve both for low-temperature stability |
| Manual vs automated read | Manual `Measure` = one 0.7 s read; the automated cycle averages **four** |
| Spectrometer diffusers | A white plastic sheet behind the aperture *"reduce[s] noise by about a factor of 10"* — retrofitted by post to owners of older units |
| Vial diameter | Hardware page says 25 mm; the forum says **24.5 mm or less** |
| Laser diode quality | The BOM warns some `ADL65052TL` suppliers ship *"as much as 10% defective stock"* |
| Thread exhaustion | `RuntimeError: can't start new thread` inside `runWatchdog` after ~1 week — a real, logged, **unresolved** upstream failure mode |
| Long-run positive datum | *"we have done experiments of a month or more"*; *"I've left them on for six months at a time"* |

### 3.5 Commerce — the V1 board is end-of-life

LabMaker: *"**LIMITED SUPPLY OF 7-COLOR LED Chi.Bio REACTOR UNITS**… This is due to end-of-life for
the 7-color LED."* Corroborated on the forum: the LZ7 stockpile bought when discontinuation was
announced is now the last batch. **Every Chi.Bio bought from here on is V2**, so this fork's
V2/GFP caveat is permanent. The V1→V2 split is a **supply-chain substitution, not a designed
revision** (GitHub issue #15).

Also: chi.bio's Buy page (US$990) is ~20% stale against LabMaker's actual US$1,190, and **three
official sources disagree about the V2 wavelength set**. This fork matches chi.bio's tech-specs,
which is the right call — but nm labels are nominal to roughly ±10 nm.

---

## 4. The code — upstream, forks, and adjacent tooling

**Upstream is frozen and its issue tracker is the real content.** Last maintainer commit
2024-04-25; the newest commit on `master` is this fork's PR #19. 39 forks, of which **12 + 4 side
branches** actually diverge. 4 of 7 open items are unmerged PRs, the oldest since 2020.
`git merge-base` confirms **this fork is at upstream HEAD — there is nothing to pull.**

**The CSV-header loop closes on this repo.** Upstream commit `dee1b5a1` (Apr 2024) added V2 LED
columns to the data rows but not to `fieldnames` → **headerless CSVs on every V2 device for ~22
months**. Reported on the forum May 2025 (Steel couldn't reproduce it), diagnosed in still-open
PR #17, and fixed upstream by PR #19 **from this repo**. This fork's `csv.DictWriter` convention is
the structural fix — the strongest single argument in the grey literature for the refactor.

### 4.1 Two upstream bugs this fork still carries, with published fixes

Both verified present in `chibio_experiment.py::PumpModulation`; both fixed in `alje-lab/ChiBio`.

1. **Duplicated `setPWM` off-pairs** at `:26–29` and `:59–62` — 4 redundant I²C transactions per
   pump per cycle, each taking the global lock and switching the mux. With 5 reactors × 4 pumps
   that is real pressure on the very resource whose contention causes the crashes in issue #16.
2. **Pump timing uses `datetime.now()` + `round(…,2)` + `time.sleep(Ontime)`.** The fix is
   `perf_counter`, `round(…,5)`, and a **spin-wait below 0.5 s** because `time.sleep` overshoots
   badly at short durations on this hardware. `round(…,2)` alone quantises to 10 ms. **This is a
   quiet quantitative error in every dilution volume**, i.e. in the dilution rate that growth-rate
   estimates are computed from. A third commit logs the achieved on-time in ms.

### 4.2 The finding that contradicts a documented assumption

`CLAUDE.md` states that no code path makes reactor identity change the OD math, so accuracy is
purely a function of blanking. **Three independent groups each fitted a different per-reactor OD
curve against a dilution series:**

| Group | Form | Spread across their reactors |
|---|---|---|
| Imperial GBS (`zoltuz@imperial_GBS`) | quadratic `a·raw² + b·raw`, in `config/device_config.csv` | quad 0.086–0.268 (~3×), lin 0.537–1.077 (2×), r² 0.90–0.99, **n=16** |
| Inria InBio (ReacSight) | cubic with a constant term | all four coefficients differ, **n=8** |
| Mitri lab (`nahanoo/ChiBioFlow`) | exponential `m·exp(−t·OD)`, calibrated to **OD ~6** | fitted per reactor, **n=8** |

**32 reactors of evidence.** The claim is true *of this codebase* and may still be adequate at
OD ≈ 0.5, but it should be stated as **untested here**. Concrete test: a 6–8 point dilution series
on two reactors, blanked normally, fitted independently; if the fits differ beyond the blank's σ,
adopt a coefficient file.

### 4.3 Forks worth borrowing from

- **`zoltuz/ChiBio @ imperial_GBS`** (53 commits ahead) — the richest fork. **Logs raw
  unnormalised FP emissions** (`FP{1,2,3}_emit{1,2}_raw`, captured before the Clear division) plus
  **`od_raw`**; **per-wavelength saturation attribution** rather than one blanket flag; structured
  logging with **`DeviceID` in every message**; a config layer (upstream PR #4, open 6.5 years)
  including `CONTINUOUS_STIRRING` — whose rationale is a bench fact: *"Continuous stirring prevents
  the magnetic bar from getting stuck at the bottom of the glass tube."*
- **`ljm176/ChiBio`** — **an actual ALE mode**: `RegulateOD` splits its computed inflow between two
  reservoirs (`Pump1 × (1−ratio)`, `Pump3 × ratio`) and ramps the ratio from 5% to 100% challenge
  medium. **Caveat found by reading the code: the growth-rate gating is written but dead**
  (`targetMet` is computed and never used); the ratio advances on a bare 10-cycle timer. Borrow the
  design, not the diff. This also settles the "no confirmed ALE" gap from the software side.
- **`Janmorlock/ChiBio`** — **automated OD blanking**: stir on 1 s → stir off → **settle 5 s** →
  **5× `MeasureOD`** → mean, storing `OD0['std']`. Addresses the manual-blank friction, respects
  the ≥5 s read spacing this fork documented, and yields a per-blank quality number. Also an EKF +
  PID composition controller that feeds `z = [OD, FP1.Emit1 × FP1.Base]` — i.e. **re-multiplies the
  ratio back by the base to recover a pseudo-raw emission**, a tacit admission that the ratiometric
  value is the wrong quantity to model.
- **`colabbear/ChiBio`** — the only fork treating "unattended for days" as the design problem:
  per-reactor **pause-on-mux-failure with an explicit operator resume route**, Discord alerts,
  per-reactor cycle/total time, and **sub-cycle pump pulse metering** with a `perf_counter_ns`
  busy-wait for flows below one on-pulse per minute. *(The quarantine idea is right; the
  implementation must not bypass `turnEverythingOff` or the global kill.)*
- **`HaxbyH/ChiBio`** — a manual **sampling event log** (label, auto-number, volume, wall clock →
  two CSV columns) and an explicit **inoculation marker**, so t=0 for biology is distinguishable
  from t=0 for the software.
- **`tauzn-clock/ChiBio`** — an EKF whose **measurement model is the photodiode current, not OD**
  (`h(x) = I₀·10^(−OD)`), i.e. it filters where the noise actually lives. Constants unvalidated;
  `GOFFREDOpy` is the rigorous version. Also `tools/set_time.sh`: **the BeagleBone has no RTC and
  drifts**, silently corrupting long-run timestamps.
- **`fuzue/chibio-next`** — an independent hexagonal rewrite with a simulated adapter and **a
  regression suite that replays a real M1 dataset through the new controllers**. Philosophical
  twin; unvalidated on hardware by their own admission.
- **`harmsm/ChiBio`** — `setup.sh` hygiene (root-guard, `INSTALL_DIR`, destructive bits commented
  out). Upstream's `setup.sh`, which this fork inherits, enables root SSH with password `root`.

**Off-device modes have now been independently invented four times** (`dr3y`'s `usecomms`,
`nadanai263`'s `ChiSim.py`, `fuzue`'s simulated adapter, `primbiolab`'s dev launcher) — decent
evidence the feature belongs upstream, and `CHIBIO_SIM=1` is the strongest of them.

### 4.4 Hardware publication

`BOM13.zip` (V1.3) ships 18 boards with Gerbers, drill files, per-board BOMs, pick-place and
assembly PDFs — and **not a single editable schematic or PCB source**. That is exactly issue #15's
complaint, unresolved 2.5 years on, and matches ModuloStat's independent scoring of Chi.Bio's PCB
and physical objects as *reproducible-from-drawings, not open-source*. Confirmed parts: **TCA9548A**
mux, **MCP9808**, **MLX90614** (DCC), **AS7341**, **PCA9685** PWM, **LZ7** LED, **ADL65052TL**
laser. **Still unsourced:** the A0/A1/A2 strapping that fixes the mux at 0x74 — a schematic net.

---

## 5. The comparative landscape

**There is no published experimental head-to-head involving Chi.Bio.** The one comparison table
that exists — **ModuloStat** (Guérin et al., ACS Omega 2026, PMC12809586) — scores it in a
17-platform matrix at **max run time 1.7 days** (vs eVOLVER 68 d, Omnistat 58 d, Marlière 166 d)
with **dilution-rate feedback only**, where seven peers also do chemical composition. The 1.7 d
figure is falsified by several papers here (7 d, 8 d, 14 d, >200 h, 150 d) — but it is a fair
reading of the *published demonstration*, and reviewers score what was published.

The nearest thing to a head-to-head is **Denton 2024's** 20 mL Chi.Bio vs a 1 L Applikon:
statistically equivalent PET conversion with 20× less enzyme, but visibly worse control fidelity.

**Pioreactor** (Raspberry Pi, ~same scale and price band) is the richest source of transferable
practice, and it already ships three things this review identifies as Chi.Bio gaps:

- **Calibration as a versioned artifact, not a runtime variable.** Run as explicit protocols
  (`pio calibrations run --device od90 --protocol standards`); **multi-point against a reference
  instrument**, not a single blank; **named, saved to disk, editable, exportable as YAML**, one
  marked *active* per device, with an explicit **staleness policy** ("recommend running
  calibrations every 6 months"). Separate calibrations for OD, each pump, and stirring — pump
  calibration being **duration → volume by weighing**, because *"there is no liquid feedback loop"*.
  **Chi.Bio has exactly the same open-loop pump problem and no equivalent.**
- **Freshness, not just validity.** *"Readings older than 5 minutes are treated as stale, and the
  automation will warn instead of continuing with a dilution based on old data."* `latest_od` is a
  property that **raises** rather than returning a stale value. `evolver-ng` formalises the same
  thing differently: `skip_control_on_read_failure`, controllers that only *propose*, a separate
  `commit_proposals()`, and an `abort()` that disables control and turns every effector off.
  **This fork's `valid=0` + last-known-value is correct for the UI and wrong for `RegulateOD`** —
  freshness is the missing half.
- **Declarative Experiment Profiles** — the condition→action layer ReacSight recommended, already
  designed as versioned YAML: quoted `version:`, `metadata`, `common:`/per-reactor blocks (→ M0–M4),
  actions `start/stop/pause/resume/update/log/when/repeat`, `t:` offsets with unit suffixes, `if:`
  conditions over live state, `${{ }}` interpolation, `hours_elapsed()`, **`when: wait_until:`
  (fire once when a condition first becomes true)**, and — critically — **a dry-run mode that logs
  what it *would* have done**. A scheduled-dosing feature you cannot rehearse is one nobody will
  trust with a 150-day run.
- Plus a stock **`PID Morbidostat`** — the automation Chi.Bio has been asked for twice in six years.

Two other transferable items: **Toprak's classic morbidostat protocol** names *"OD does not change
after media injections"* → **biofilms on the inner wall** as *the* wall-growth signature, and makes
**daily vessel swap** and a **daily glycerol archive** ▲CRITICAL steps; and **EVE** (eLife 2022)
plus Pioreactor hold the **education niche Chi.Bio's marketing claims** — iGEM teams that wanted a
turbidostat *rebuilt the feature set on Arduino* rather than buy one, one team explicitly citing
turbidostat cost.

---

## 6. Domain verdicts

Three independent sweeps (citation graph, full-text index, forum), so a negative means three
indexes agree.

| Domain | Verdict | Basis |
|---|---|---|
| ALE / mutagenesis / directed evolution | **CONFIRMED — overturns revision 1** | 6 works, incl. Steel's own lab |
| Consortia / ecology / cross-feeding | **CONFIRMED** | 4+ works, two actuation strategies |
| Circuit characterisation & absolute quantification | **CONFIRMED** + a protocol chapter | 4 works |
| Quantitative physiology / growth-rate methods | **CONFIRMED** | 4 works + an R tool |
| Non-model bacteria | **CONFIRMED** | 4 works |
| Yeast beyond the metrology paper | **CONFIRMED** | 2 works |
| Bioproduction / metabolic engineering | **CONFIRMED** | 3 works |
| Batch / media screening | **CONFIRMED** | 6 works never touch the pumps |
| **Morbidostat operation** | **NOT IMPLEMENTED** | 6-year-old, twice-asked, unanswered |
| Cyanobacteria / phototrophs | **EMPTY in literature — but explained** | See below |
| Biofilms *(as a study subject)* | **EMPTY** | Clean negative; but see C3 — biofilm *monitoring* is in Steel 2020 |
| Anaerobes | **EMPTY** | Vessel is open to atmosphere; the niche went to AneVO |
| Phage–host | **EMPTY** | The one Steel-lab preprint is **simulation only** — verified, zero Chi.Bio mentions. Do not cite it as a use. |
| Teaching / iGEM | **EMPTY** | Niche lost to EVE/Pioreactor |
| Antibiotic MIC / persistence | **EMPTY** | A surprising gap given the feature set |
| Mammalian / insect / cell-free | **EMPTY** | Architecturally expected |

**Cyanobacteria is the informative negative.** Steel on the forum: *"We have done both of these
things in our lab… using the white (6500 K) LED at low intensity to support cyanobacteria growth,
and also using CO₂ to pump through the headspace"* (~0.1 L/min) — **unpublished**. The blocker is
optical: *"At 650 nm there is overlap with emission of chlorophylls"*; the conventional read is
**OD750**. Steel's fix is to **desolder the 650 nm diode and drop in a ~700–800 nm one with the
same pinout** (~$10), reusing the control circuit. Asked in 2022, re-asked May 2026, **no reported
outcome**. *Implication:* if anyone swaps the diode, nothing in the software records that the
wavelength changed — the CSV would silently still claim OD650.

⚠ One caution for the record: a web-search summariser asserted "Chi.Bio can be used to monitor the
growth of biofilms" in a context that could not be traced. The *real* citation is Steel 2020
Application 1 / supplement S1O. Don't propagate untraced snippets.

---

## 7. Synthesis — the directions, ranked

Revision 1's ranking survives with **one promotion, one demotion, and two new top-tier items**.

### Do first — cheap, high-consequence, and revision 1 did not have them

1. **Log raw OD (`OD0.raw`) to the CSV, and record the optical configuration in the sidecar.**
   Chi.Bio computes the raw laser value and discards it; combined with a RAM-only blank, a restart
   silently changes the meaning of the OD column with no way to undo it. This is the fork's
   documented 2–3 place edit, composes with the existing `logEvent` blank records, and is a
   precondition for any retrospective re-blanking or `k·log₁₀(R)+b` conversion. Sidecar should
   carry OD source/wavelength, `LASERa`/`LASERb`, blank value + timestamp, and LED version.
   *(zoltuz's `od_raw`; Ulrich & Mitri; the cyanobacteria diode-swap scenario.)*
2. **Log raw, unnormalised FP emissions** (`FP{n}_emit{1,2}_raw`, before the Clear division). This
   is the **only** way to retro-fit matched-control subtraction onto data already collected — the
   exact remedy every source prescribes — and this fork currently stores ratios only.
   *(zoltuz; and `Janmorlock` re-multiplying `Emit × Base` to recover it.)*
3. **Fix the two pump bugs** ([§4.1](#41-two-upstream-bugs-this-fork-still-carries-with-published-fixes)):
   delete the duplicated `setPWM` off-pairs; move to `perf_counter` + spin-wait + `round(…,5)`, and
   log achieved on-time. ~6 lines, in the path that meters every dilution.
4. **Fix the AS7341 saturation handling** ([§1.4](#14-the-as7341-itself)): compute full scale as
   `min(65535, (ATIME+1)×(ASTEP+1))` rather than a bare constant — the LED V1/V2 auto-detection at
   `ISteps=10` saturates at 11,000 and cannot currently be seen to have saturated, a live path to
   misdetecting a V2 board as V1. Un-comment the `STATUS2`/`ASTATUS` read and fold `ASAT_ANALOG`
   into the `valid` flag; retune `_FP_BASE_NEAR_SATURATION` toward ams' 87.5% (57343).

### Do next — the most corroborated gap in the review (promoted from #2)

5. **Scheduled dosing / declarative experiment profiles.** Six papers, six forum threads, an
   outside benchmark naming it as a missing capability category, and a working precedent in
   `ljm176`'s two-reservoir ratio ramp. Design points: adopt Pioreactor's YAML schema rather than
   inventing one; **`when: wait_until:`** covers Wenk's staged ramps and Joshi's timed swaps; a
   **cumulative-volume interlock** (from the pH mod) is mandatory; and a **dry-run mode** is what
   makes it trustworthy for a long run. Generalise beyond media: the selective pressure is almost
   never the dilution loop — it is medium composition (Wenk, Klass), **temperature** (Deng, Lee),
   **UV** (Corrao), or antibiotic (Guyot). All want the same primitive: *a scheduled or
   feedback-driven trajectory for one actuator.*
6. **A morbidostat / stressor-hold automation, using the control law Steel published.** PI on
   growth rate, setpoint at ~1/3–1/2 of uninhibited, and — the non-obvious part — **exponentiate
   the controller output**. Make the actuator pluggable: pump ratio or UV intensity. Closing the
   loop on growth rate also sidesteps the UV LED's total lack of dosimetry.

### The fluorescence track — now split into two separable deliverables

7. **(a) Trustworthiness.** Matched non-fluorescent-control subtraction as a first-class FP mode
   — **the vendor's own protocol**; per-reactor zero on cells+media, subtracted to a common
   baseline. Pre-induction baseline subtraction (30 min mean) as the standard background rule.
   Cross-channel bleed-through correction for the GFP+RFP pair. A GUI sub-detectability warning
   quoting the vendor's own floor (*"<0.5% of the brightest GFP cells you have ever seen"*) plus the
   **LB-vs-M9 media warning**, and an explicit note that **raising gain or power does not help**.
   ±10 nm tolerance on the Stokes-shift arithmetic, and a comment recording `_gain_multiplier`'s
   ~7% systematic error.
   **(b) Comparability.** MEFL + particles units with Díaz-Iza's two-stage structure (expensive
   once-only off-device bead/fluorescein calibration; cheap on-device re-calibration needing only a
   culture), and an automated calibration wizard using their *dilute-to-a-sensor-marker* trick.
   **(a) gates (b)** — and note Sambruna's finding that a per-device *scalar* is insufficient
   because the correction is concentration-dependent.
   ⚠ **Before building: obtain the Methods Mol Biol 3041 chapter.** It is the source lab's own
   51-page protocol for exactly this, with troubleshooting.

### Worth doing

8. **Orchestration hooks — promoted, and for a new reason.** Revision 1 ranked this on ReacSight's
   *success*; the stronger case is the *failure*: a major control group polling a CSV over SFTP on
   a machine that is already an HTTP server, and JHU APL federating 16 reactors over REST. New hard
   requirement revision 1 did not capture: **per-`M` addressing that does not go through
   `changeDevice`**, because two coupled reactors must be driven from one process. Minimum viable:
   a documented measurement snapshot + per-reactor actuator setpoints with an expiry, and a note
   that the cadence is ~1 min.
9. **Freshness alongside validity.** Timestamp every reading; have `RegulateOD` and `Thermostat`
   decline-and-warn on stale or invalid input; put actuation behind a distinct commit step.
10. **Automate OD blanking** (stir → settle 5 s → 5 replicates → mean + σ) and **persist the
    blank across restarts**. Two of the most common ways a long run is silently ruined.
11. **Optogenetic control depth:** duty-cycle/pulse-train programs, multi-λ combos, inverted
    programs, **scheduled darkness**, and a **log-scaled intensity input with a phototoxicity note**
    — the useful region for at least one common sensor sits at the very bottom of the dial.
12. **Fouling alarms computable from data already logged:** OD failing to fall after a commanded
    dilution (the wall-growth signature); a rising input pump rate at stable OD (S1O's biofilm
    relation); spikes in the spread this fork already computes; and the *inferred* per-cycle
    dilution, which also gives free QC on tubing wear.
13. **Extend the events log to operator actions** — sampling events (label, volume, timestamp) and
    an explicit **inoculation marker** — for the offline-cytometry workflow everyone actually uses.
14. **Verify the CSV loads into `chemostat_regression` unmodified.** A published, peer-reviewed
    analysis path in R + ggplot2, essentially free. Keep the pump-rate columns honestly 0 when off.
15. **Write down a sterility protocol.** The fork has none. Two independent groups converged on:
    assemble the passive fluidic circuit, **autoclave it as one closed unit**, then seat tubing
    into the pump heads **without opening the circuit**. Add the two known contamination pathways
    (pump-head backflow into the media bottle; wall growth as the binding constraint on run length)
    and the filtered-vent/check-valve recipe from Lee et al.

### Preserve — now with vendor citations

16. The **deliberate whole-system crash** on unrecoverable mux failure is designed: Steel warns
    explicitly against defeating it, because the hardware kill is what stops a stuck pump
    overflowing a vessel. The **mux hard-reset via GPIO** is the sanctioned recovery on V1.2+
    boards. **Ratiometric-as-default until the FP rework lands** — Steel confirms it removes ~90%
    of the OD dependence; imperfect, not useless. The **PII's second integrator** compensates
    degraded pump suction — not cruft. **`--timeout 300`** is independently corroborated by two
    upstream issues. **Binding to `192.168.7.2`** is the supported path; Ethernet is a known-unstable
    one. Bounded replication, the I²C chokepoint, `valid=0` semantics, and per-reactor blanking all
    match what the primer and the supplement describe.

### Note for the repo's own docs

Three corrections in [§0](#0-corrections-to-revision-1) have propagated beyond this file and
should be fixed at source: the `60000` guard's provenance and the Joshi framing in `CLAUDE.md`,
and the dead-code analogy at `TODO.md:104`. Separately, `CLAUDE.md`'s "reactor identity never
enters the OD math" should be restated as **untested here** ([§4.2](#42-the-finding-that-contradicts-a-documented-assumption)).

---

## 8. Coverage, confidence, and what remains unread

**Enumerated:** 113 distinct citing works (Semantic Scholar 83; OpenAlex 100 + 13 for the
preprint; deduplicated), 91 OpenAlex full-text hits, 35 Europe PMC full-text hits, all 189 forum
topics, all 18 upstream issues/PRs, 35 of 39 forks compared via the GitHub API, and the complete
chi.bio sitemap.

**Read in full:** 31 full texts retrieved and grepped for Methods-level use (17 PMC, 14 bioRxiv
JATS); the 49-page Steel supplement; the ReacSight Supplementary Note and its Chi.Bio `app.py`;
the Sambruna PDF with figures rendered; the AS7341 datasheet; the official BOM v1.3; two theses;
and the substantive fork diffs.

**Triage rule:** a work counted only if Chi.Bio produced data in Methods/Results, was
modified/extended, was benchmarked or independently calibrated, or the work publishes tooling
consuming Chi.Bio output. Reference-only mentions were rejected **on full-text evidence, not on
the abstract** — which caught several false positives, including a paper whose title promised
automated mini-bioreactors but which used a **Pioreactor**, and a di Bernardo-group paper with
zero Chi.Bio mentions.

**Highest-value items still unread** *(status updated by revision 3 — see [§9](#9-revision-3--the-deep-read-2026-08-13))*:

1. ~~**Methods Mol Biol 3041:145–195**~~ — **largely resolved (§9.2, §9.4).** Abstract now
   exposed in PubMed; and the chapter is reference [90] of the Stacey sponge-RNA preprint, whose
   open Methods carry the operating protocol and the per-reactor `y = mx + c` FPCountR
   conversion. Buying the chapter would add troubleshooting detail, not the method. The
   "companion chapter `…_13`" claim was **wrong** — it is a co-culture cybergenetics chapter.
2. ~~**Pen, Nunn & Goyal 2021**~~ — **identified (§9.2, §9.5).** ACS Synth Biol 10(4):766–777,
   `10.1021/acssynbio.0c00574`. Still closed-access, but the architecture is now known from its
   abstract and secondary descriptions: fibre-bundle probe + microPMT, 30 mL vial — the same
   optical front end Sambruna recommends as the fix.
3. **Supplementary information was not fetched for any paper.** Several relevant numbers live
   there (Lee's Chi.Bio fluorescence characterisation; Lazar's light-intensity calibration;
   Stacey's per-reactor conversion curves).
4. **ProQuest and CORE were not swept** — three dissertations surfaced from OpenAlex alone, so more
   likely exist. No Steel-lab DPhil thesis was found in Oxford ORA, which is surprising.
5. **ams SMUX/calibration application notes** — `look.ams-osram.com` serves an empty body.
6. **The mux's 0x74 strapping** is a schematic net; the public archive ships Gerbers only.

**Known negatives worth trusting:** arXiv is exhausted beyond the two di Bernardo works;
TechRxiv, SSRN, Preprints.org, engrXiv/OSF and medRxiv are dry; there is no Chi.Bio Slack,
Discord, mailing list, wiki, webinar, video or teaching pack — the bbPress forum is the sole
community channel. GitLab/Bitbucket/OSF/protocols.io/Hackaday searches found no Chi.Bio-specific
code, though those platforms have weak site search and that negative is weaker than the GitHub one.

**One item never retrieved:** Pentz et al. 2024 bioRxiv (`10.1101/2024.11.20.624476`) — HTTP 500
across two sessions; characterised from its abstract plus the authors' companion STAR Protocols
paper, which does name Chi.Bio.

---

## 9. Revision 3 — the deep read (2026-08-13)

Revision 2 closed with a list of "highest-value items still unread" (§8). This revision reads
three of them and re-runs the corpus search. **The search found nothing new** — which is itself
a result, and is reported first so it is not mistaken for a gap.

### 9.1 The corpus is closed (for now)

Re-run 2026-08-13, two days after revision 2:

| Avenue | Method | Result |
|---|---|---|
| PubMed | `Steel H[Author] AND bioreactor`; `Sechkar K[Author]`; title searches | 0 new works |
| Europe PMC | exact phrase `"Chi.Bio"` full-text | **35 hits — identical to revision 2's count** |
| Europe PMC | fuzzy `"ChiBio"` | 20 hits, all either already held or tokeniser noise (chitosan, chito-oligosaccharide, liposome papers — verified false positives by re-querying each with `EXT_ID` + the exact phrase, which returns 0) |
| Fork network | `HarrisonSteel/ChiBio` forks by `pushed_at` | 39 forks, no new divergent one; upstream last pushed 2026-02-10 |

Two works surfaced that revision 2 does **not** cite, and both are correctly excluded by the
triage rule (reference-only mentions, no Chi.Bio-produced data): Espinel-Ríos 2025, *Front Syst
Biol* 5:1583534, a bioengineering-education perspective; and Jang & Avalos 2025, *FEMS Yeast Res*
25, an optogenetics-in-yeast review. Everything else that looked new — Lazar/Tabor's green light
sensor, Klass's malonyl-CoA work, Deng's gene syntaxes, Droghetti/Tallarico's damped
oscillations, Olivi's DnaA, Guyot's qB2H, Guérin's ModuloStat, Koehler/Pentz's STAR Protocols —
is already in revision 2 under an author name the topic search did not match.

**Conclusion: breadth is done.** Further effort belongs in depth (below), in the supplements
(§8 item 3, still unfetched), and in the two databases never swept (ProQuest, CORE).

### 9.2 Corrections to revision 2

- **MMB `…_13` is not a calibration companion.** §8 called it a "companion chapter" to the
  calibration protocol. It is **Lee, Stacey, Gallup, Steel & Sechkar 2026, "Dynamic Robust
  Control of Microbial Communities Using Cybergenetics", *Methods Mol Biol* 3041:261–285**
  (`10.1007/978-1-0716-5304-3_13`) — a co-culture cybergenetics methodology chapter, the
  book-chapter form of the Lee 2025 *Cell Rep Methods* work. Relevant, but not about calibration.
- **Both MMB chapters are now abstracted in PubMed.** §8 recorded them as "paywalled, no abstract
  exposed". Both now carry full abstracts, which is how the above was settled.
- **The calibration chapter has a freely-readable primary paper.** MMB 3041:145–195 is cited as
  reference **[90]** by the Stacey sponge-RNA preprint — i.e. the chapter *is* the full protocol
  behind that preprint's Methods, and the preprint's Methods are open. §8 item 1 is therefore
  substantially satisfied without buying the chapter (§9.4).
- **Pen, Nunn & Goyal 2021 is identified** (§8 item 2, previously known only by citation): *"An
  Automated Tabletop Continuous Culturing System with Multicolor Fluorescence Monitoring for
  Microbial Gene Expression and Long-Term Population Dynamics"*, ACS Synth Biol **10(4):766–777**,
  `10.1021/acssynbio.0c00574` (PMID 33819013). Still closed-access, but its architecture is now
  known and it matters (§9.5).

### 9.3 Sambruna, Tallarico & Cosentino Lagomarsino 2026, read in full

bioRxiv `10.64898/2026.06.29.735387`, posted 2026-07-09, CC-BY. Revision 2 characterised this
from the PDF; the full text adds Methods and four results that change what we should do.

**They tested our exact strain.** Their *E. coli* arm is **fixed TB204 expressing sfGFP** —
`MG1655 attP21::PR-sfGFP`, Addgene 230033, the same isogenic strain our runbook assigns to M3 as
"the worst case on V2, the one the track exists for". Their result on it: raw intensities scale
linearly with cell concentration but show **no clear separation** from wild-type; the
signal-to-background ratio "fluctuated around unity", with **only two concentrations exceeding a
10% discrepancy threshold**. After ratiometric normalisation a marginal separation appears, but
"the magnitude of this separation was comparable to the inter-device variability".

**Their four results, with the numbers:**

1. **Beads work, cells do not.** Both microsphere types scale linearly with concentration, and
   net intensity after subtracting a matched non-fluorescent bead has an **intercept close to
   zero**. Fixed Rpl5-GFP *S. cerevisiae*: S/B ≈ 1, no discernible peak at the GFP emission
   region. The same samples separate cleanly in a monochromator plate reader — so it is the
   instrument, not the expression level.
2. **Ratiometric normalisation fails at both ends, analytically.** Writing the normalised
   intensity as `(a·c + b) / (a_C·c + b_C)`, the concentration-independent backgrounds `b`, `b_C`
   dominate at low `c`, and Clear saturation at **65535** offsets it at high `c`. **The failure
   mode named for the first time: "particularly problematic in dynamic experiments with periodic
   dilutions, where the normalization generates artifactual signal changes that can be mistaken
   for biological responses."** That is a turbidostat, i.e. exactly our operating mode.
3. **Inter-device variability is the binding constraint, and it is not an offset.** Net signal ÷
   σ_device fluctuates around **3.3** — above the noise on average, but not consistently.
   KDE per device shows peak positions shifting between devices, and Figure 5C shows
   **"device-specific concentration trends that cannot be corrected by a simple additive
   offset"**. Beads, by contrast, stay separated across all devices — proving the problem is
   sensitivity on dim samples, not a broken instrument.
4. **Four practical guidelines**, from their data plus direct correspondence with Steel:
   - non-fluorescent media (LB autofluorescence "significantly increases background");
   - **design the experiment to induce from a zero-signal baseline** — start uninduced and
     subtract the pre-induction baseline — **rather than comparing two steady-state conditions**;
   - per-device calibration against a fluorescent reference standard before any cross-device
     comparison;
   - **verify the expected signal in a more sensitive reference instrument before committing.**

**Their bead protocol, which is directly executable here** (Methods, Table 1): Fluoresbrite YG
Carboxylate 1.00 ± 0.03 µm (nominal ex/em 441/486); PS-FluoRed 0.98 ± 0.03 µm (530/607);
non-fluorescent amino-polystyrene **AP-10-10**, 1.0–1.4 µm (Spherotech) as the matched blank.
Diluted in Milli-Q water into standard Chi.Bio vials prefilled with **20 mL**, over
**0.2 × 10⁷ – 3.4 × 10⁷ particles/mL**. Settings: **gain ×512, power 0.1** for beads, **power
0.01** for cells; ex/em **395/510** (YG) and **523/620** (pink); **457/510** for GFP cells. Five
reactors on a shared controller, thermostat and pumps off, ambient temperature.

**Their hardware suggestions**, if sensitivity is ever the goal: fibre-couple a dedicated
visible-range spectrometer plus a high-pass filter to cut the excitation leak, or bolt on an
external flow cytometer (as two cited groups did).

### 9.4 The Oxford lab's own Chi.Bio operating protocol

From the Methods of **Stacey, Sechkar, Corrao, Steel & Papachristodoulou 2026**, bioRxiv
`10.64898/2026.05.19.726096` — the primary paper whose full protocol is MMB 3041:145–195. This is
the closest thing that exists to a reference operating procedure from the people who built the
device, and several details differ from ours:

- **Medium M9 with antibiotics**, 37 °C, **stirring 0.5**, ~20 mL — our settings exactly.
- **Vials autoclaved, then cleaned with ethanol *and dried*; media and waste tubing flushed with
  70% ethanol.** Note "and dried": `INVARIANTS.md` §6 lists *residual ethanol from vial wiping*
  as an untested candidate for M0's unexplained slow growth, and the source lab treats drying as
  an explicit step rather than an afterthought.
- **Blank, then a 15-minute stability check, then re-blank if needed.** Verbatim: *"Experiments
  ran for a further 15 minutes to confirm OD blanking stability, after which any further blanking
  was performed."* Preceded by 15 min of temperature equilibration before the first blank. **We
  do neither** — we blank once and proceed.
- Turbidostat **setpoint 0.5** with **OD dithering enabled for growth-rate calculation** (our
  `Zigzag`); inoculated with **200 µL**.
- **Fluorescence settings: GFPmut3 = 457 nm excitation / 510 nm emission**; mScarlet-I = 523/583
  **or** 595/670. The 457/510 choice independently confirms the LEDB→nm510 "least-bad readout"
  this fork already surfaces in the V2 GFP caveat.
- **Absolute quantification is per reactor, and it is a line not a scalar.** They adapt FPCountR
  (Csibra & Stan, *Nat Commun* 13:6600, 2022) by sampling the reactor around induction events and
  measuring those samples in a plate reader at fixed settings, then: *"For each Chi.Bio reactor,
  data across experiments were pooled and linear models of the form **y = mx + c** were fitted in
  R describing conversion from processed Chi.Bio fluorescence to molar concentration."*
  A per-reactor **slope and intercept**, fitted against an offline instrument — consistent with
  Sambruna's finding that an additive offset alone is insufficient.
- **Inducer step-changes are entirely manual**: disable OD control, empty the input line to
  waste, swap the media bottle, wash the pumps through to waste, add 1 mL of inducer in M9 per
  vial, reconnect, re-enable. This is the third independent instance of the capability gap the
  P8 schedule work addresses, and the most precisely documented.
- **Growth rate is estimated with a Bayesian filter, not a smoother.** `GOFFREDOpy`
  (Corrao 2026, already in §4.3) with measurement-noise SD **0.005**, adaptivity **0.15**, 1%
  outlier-rejection confidence, verified by testing for absent autocorrelation of innovations up
  to 5 lags, then a **21-point symmetric moving average** before model fitting. Our estimator is
  an EWMA with learning rate 0.05 and no outlier rejection.

### 9.5 Pen, Nunn & Goyal 2021 — what "high dynamic range" actually bought

Revision 2 flagged this as the one platform claiming precisely the capability Chi.Bio lacks.
It is a 30 mL cylindrical vial with turbidostat/chemostat modes, and — the part that matters —
fluorescence is read through a **multi-fibre optic bundle probe** carrying excitation from LEDs
into the culture and guiding emission to a **microPMT**, not through a chip spectrometer at 90°.

That is the same architecture Sambruna recommends as the fix (fibre-coupled spectrometer + a
high-pass filter). Two independent sources, one by construction and one by measurement,
therefore converge on the same conclusion: **the sensitivity limit is the optical front end, and
no amount of software fixes it.** This closes the argument that began with the Fluorostat 2015
result in §1.3 — it is now three independent lines, not two.

### 9.6 What revision 3 changes for this fork

1. **The Run 1 sfGFP arm has a published expected result on the identical strain.** TB204 in a
   Chi.Bio gives S/B ≈ 1. Run it as a **confirmation with a pre-declared decision rule**, not as
   an open question — and take Sambruna's fourth guideline seriously: measure the inoculum in a
   plate reader first, so the run starts knowing whether the signal exists at all.
2. **Our constitutive strains cannot follow the best-practice design.** The recommended design is
   induce-from-zero with pre-induction baseline subtraction. `attP21::PR-FP` is constitutive, so
   the only available design is the steady-state comparison they explicitly advise against. That
   is not fatal — matched-control subtraction is the fallback they endorse — but it should be
   written down as a known limitation of the panel rather than discovered later.
3. **Making matched-control subtraction first-class in the FP path is now the best-evidenced item
   in the backlog** (TODO P5 item 316). The new argument is not "ratios are imprecise" but that
   ratiometric normalisation *manufactures artifacts synchronised with dilution events* — in a
   turbidostat, a signal that looks like a biological response.
4. **The per-device calibration item has a concrete recipe and a shopping list** (TODO P5 item
   319): beads per §9.3, per-reactor `y = mx + c` fitted against a plate reader per §9.4. The
   bead route is the cheap one — it needs no strain, no culture, and no sterility, and it
   measures σ_device directly rather than inferring it from cultures.
5. **Two free procedural upgrades**, both from §9.4 and both applicable to the very next run: the
   **15-minute post-blank stability check with re-blank**, and **drying after ethanol wiping**.
   The first would have caught our stale-blank failure mode; the second is a live candidate for
   the M0 mystery.
6. **`GOFFREDOpy` is worth running offline on the Run 0 CSV.** It needs only `time`,
   `od_measured` and a `growth`/`dilution` transition label, all of which we log, and it returns
   per-point covariance and an outlier flag. Zero device risk — it is post-hoc analysis — and it
   would say whether our EWMA growth rates are trustworthy, including for M0.
