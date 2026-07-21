# Prep plan — matched non-fluorescent control experiment

Prepared 2026-07-20; revised 2026-07-21 after correcting the hardware count to **5 reactors**
(the earlier 7-reactor design assumed 8 slots — see §1 for what got cut).
Bench-side prep + protocol for the experiment that unblocks the fluorescence-quantification
track (`TODO.md` P5/P7 fluorescence items).

**Hardware state:** the software addresses M0–M7, but you have **five physical reactors** —
M0–M4 is the whole rig. As of 2026-07-20 only **M0 and M1 are cabled** (`presentDevices` M2–M7
= 0); cable the remaining three. After cabling, you must POST `/scanDevices/all` and confirm
`presentDevices` before measuring: the top-level `present` flag defaults to 1 for un-scanned
devices, and measuring an absent reactor drives `I2CCom` into `os._exit(4)` and trips the
watchdog on the *running* reactors.

LED hardware is **V2** (`Version.LED == 2`), excitation set:
`LEDB 457 · LEDC 500 · LEDD 523 · LEDI 550 · LEDH 600 · LEDF 623`.

**Two findings that shaped this plan:**

1. **There is no per-device OD calibration to worry about.** `LASERa`/`LASERb` come from a single
   shared template (`chibio_state.py:42`) identical for every reactor, and the per-`M0`–`M3`
   `CF` constants in `chibio_measurements.py` are **dead code** — assigned, then never used (the
   line consuming them is commented out; the live formula is `raw/OD0.target`). So M4 is no
   worse calibrated than M0–M3. The only per-reactor OD quantity is the blank, `OD0.target`,
   which you set yourself. Connecting M2–M4 costs nothing in OD accuracy.
2. **Scans are strictly serial and cost you density matching.** All reactors share one I2C bus
   behind a single global lock, so scans cannot run in parallel — a ladder point takes
   (reactors × ~1.5 min). That drift is designed around in §6. The silver lining of only having
   five reactors: a ladder point is ~7 min instead of ~10, so the within-ladder growth drift
   drops from ~11% to ~8%.

---

## 1. Design

With slots available, the control and both fluorophores go in the **same run, same media batch,
same day** — which removes the biggest confounder in the two-reactor version and eliminates the
need for separate per-fluorophore runs entirely.

**Run 0 — device cross-calibration (~½ day).** Every connected reactor gets the *same* WT
culture from one flask. This measures the reactor-to-reactor EEM offset and, more importantly,
σ_device across the whole set at once. That is exactly the "per-device fluorescence calibration
constants" TODO item, and without it you cannot tell a real FP signal from a device difference.

**Run 1 — the experiment (~1 day), all 5 reactors:**

| Slots | Contents | Role |
|---|---|---|
| 2 | MG1655 WT (no FP) | Matched non-fluorescent control, **duplicated** |
| 1 | **TB205** `attP21::PR-mCherry` | FP arm — best-served on V2, method anchor |
| 1 | **TB204** `attP21::PR-sfGFP` | FP arm — worst case on V2, the reason this track exists |
| 1 | **Sterile media, never inoculated** | Instrument/tube floor, tracked all day |

All three FP strains are isogenic (same MG1655 background, same `attP21` locus, same `PR`
promoter, single chromosomal copy, no resistance marker), so plain MG1655 is a valid matched
control with no empty-vector needed, and differences between arms reflect fluorophore and
instrument rather than expression level.

**Where the slots go, and what five costs you.** Three slots are non-negotiable. The control is
the subtrahend in every subtraction, so its noise propagates into every result — it gets n=2.
The uninoculated sterile reactor is the cheapest slot in the experiment: it separates instrument
drift over the day from biology and supplies the intercept term at *every* ladder point, not
just t=0.

That leaves **two slots for three fluorophores**, so you cannot have both an FP error bar and
sfGFP coverage. **sfGFP wins.** The fluorescence-quantification track exists because GFP-in-cells
sits at or below the detection floor on this hardware; a run that validates the method on
mCherry alone doesn't answer the question that prompted it. mCherry keeps the other slot as the
positive anchor — if subtraction fails there it fails everywhere.

**Cut relative to the 7-slot design:** the mCherry replicate (both FP arms are now n=1 — the
error bar lives on the control side and on σ_device from Run 0) and **TB201/mYFP entirely**.
mYFP is the intermediate case; once the method is validated on mCherry and characterised on
sfGFP, mYFP is a repeat of a known method rather than a new question. Run it as a follow-up on
the same rig, same media recipe, so it's comparable.

The alternative, if you'd rather have the FP error bar than sfGFP coverage, is TB205 ×2 and no
sfGFP. Do **not** buy mYFP back by dropping the WT replicate: the control's within-run variance
is load-bearing for every number in the analysis, and Run 0 gives you the device-offset map but
not that.

**All three fluorophores run together**, which the isogenic panel makes meaningful — matched
promoter, locus, and copy number mean the arms differ by fluorophore and instrument response,
not expression. Expected ordering on V2: **mCherry best** (`LEDH` 600 ≈ the paper's 595 nm RFP
excitation, read at `nm670`, clear of the `ex550` leak ridge), **mYFP intermediate**
(`ex523→nm550`), **sfGFP worst** — V2 has no ~488 nm channel (the set jumps LEDB 457 → LEDC 500),
so sfGFP is under-excited and its best cell is scatter-contaminated. Treat sfGFP as the stress
test: a negative there bounds the hardware rather than the method.

---

## 2. Strains

- **Control:** MG1655 (K-12) ancestral — **no FP, no plasmid**. This is the exact parental
  background of the FP strains, so it is the correct matched control as-is. No empty-vector
  control is needed *because* the FP is a single chromosomal copy, not plasmid-borne: there is no
  plasmid burden or copy-number difference to match.
- **FP arms:** the isogenic Addgene panel — **TB204** (`attP21::PR-sfGFP`), **TB201**
  (`attP21::PR-mYFP`), **TB205** (`attP21::PR-mCherry`), all constitutive single chromosomal
  copies at the same locus under the same promoter.
- **No antibiotics in any reactor.** Single chromosomal copy needs no selection, and keeping the
  medium identical across reactors matters more than anything else here: any compositional
  difference between a control and an FP reactor lands directly in the subtracted signal.

## 3. Media

**M9 salts + 0.2% glucose**, unchanged. Minimal and very low in autofluorescence, comparable
with the archived weekend data, and its ~OD 1–1.5 ceiling keeps you clear of the FP
Clear-channel saturation regime.

- **One batch, one bottle, one day, for all five reactors** — including the sterile blank
  reactor, which must be the same media. Do not split across preparations. Media background is
  precisely the thing subtraction cannot remove.
- **20 mL working volume per reactor** (1 mL inoculum into 19 mL) — Chi.Bio's own standard, and
  the extra headspace matters because these runs are unaerated (below). Five reactors ≈ 100 mL;
  make **500 mL** to cover overnights, washing, blanking, and spillage.
- Batch mode. No pumps or reservoirs needed for Runs 0–1.
- **Vials are vented, not sealed** (0.22 µm filter per lid). Without pumps the lid is the only
  gas exchange, and O₂ starvation both suppresses GFP/YFP chromophore maturation and raises
  NAD(P)H/flavin autofluorescence — signal down, background up. See the venting callout in the
  runbook; it is common-mode across reactors and so subtracts, but it costs absolute sensitivity.

## 4. Overnight / inoculum prep

1. Streak all four strains fresh from glycerol stocks — WT, TB204, TB201, TB205; pick single
   colonies.
2. **Grow overnights in M9 + 0.2% glucose, not LB.** LB is strongly autofluorescent and the
   carryover contaminates precisely the background you are trying to characterize; M9-adapted
   cells also skip the long lag on transfer.
3. **Grow one overnight per strain, then split it across that strain's replicate reactors**
   (WT and TB205 each occupy two slots) —
   the two TB205 reactors must come from the same flask. Otherwise "replicate" measures your
   pipetting, not the instrument.
4. Morning of: **pellet and wash once in fresh M9**, resuspend. Removes spent-media fluorophores.
5. **Normalize all four overnights to the same OD** on your benchtop spectrophotometer before
   inoculating, so every reactor starts matched.

## 5. Starting density and the scan ladder

**Inoculate to OD ≈ 0.02** — 1 mL of a washed OD ~0.45 stock into 19 mL (20 mL final).
Don't start lower; you want the whole ladder inside a working day.

At μ ≈ 0.65/h (doubling ~64 min) from OD 0.02:

| Scan point | OD | ~Time after inoculation |
|---|---|---|
| Blank | 0 (sterile media, **before** inoculation) | — |
| L1 | 0.2 | ~3.5 h |
| **L2** | **0.4 — primary point** | ~4.6 h |
| L3 | 0.6 | ~5.0 h |

OD 0.4 is where the Chi.Bio paper's own fluorescence procedure holds cells, so it's the
best-supported comparison density. Unaerated vials will run slower than these clock estimates —
trigger on measured OD.

**Scan a ladder, not a single density.** The claim under test is that matched-control
subtraction is *linear with near-zero intercept* where the ratiometric method breaks. One point
cannot test that; three points plus the sterile blank can, and **linearity through the origin is
the acceptance criterion** for the method.

**Ceiling: stop at OD ~0.6, stay off plateau.** At plateau the FP3 CLEAR base broke 60000 on
27–40% of cycles — the exact regime the new saturation guard NaNs out, so scanning there wastes
the run. The old "wait for higher density and the ratio will improve" idea was disproven on
2026-07-18: autofluorescence and scatter scale with biomass just as the FP does. Unaerated vials
give another reason not to push high: reaching 0.8 would take a long time and would do it under
progressively worse O₂ limitation.

## 6. The scan window

A `full` scan is 6 LEDs × 3 powers = 18 cells, roughly **1–1.5 min per reactor**. The I2C bus is
serialized by a single global lock, so **five reactors ≈ 6–7.5 min per ladder point**, and the
cultures keep growing throughout: at μ 0.65/h the last reactor scanned is ~8% denser than the
first. Since background scales with biomass, that drift goes straight into your subtraction if
you ignore it.

Two mitigations, both cheap:

- **Interleave the scan order so each FP reactor is adjacent to a control**:
  `WT-a → mCherry → sterile → sfGFP → WT-b`, which is plain M0→M4 order in the runbook's layout.
  With five slots this is exact — both FP arms sit directly next to a WT, and the sterile blank
  lands mid-window. Subtract using the *nearest-in-time* control, not a single global one; the
  effective control-to-sample gap is ~1.5 min.
- **Record each reactor's actual OD immediately before its own scan** and normalize per-OD
  afterwards. Do not infer density from the clock.

If drift still dominates the error budget, the upgrade is to hold every reactor at each setpoint
with the turbidostat — at the cost of pumps, reservoirs, and much more media. Don't start there.

## 7. FP logging channel

Use **all three FP slots, one per fluorophore**, set identically on every reactor including the
WT controls and the sterile blank — so every reactor logs all three channels and each FP arm has
a directly comparable control channel. Keep FP2 (mYFP) configured even though that strain isn't
in this run: it's free, it gives a third spectral point on every reactor, and the follow-up mYFP
run then inherits a validated configuration. Each slot takes two emission bands, covering both
candidate readouts per FP:

| Slot | Excite | Emit1 / Emit2 | For |
|---|---|---|---|
| FP1 | `LEDB` 457 | `nm510` / `nm550` | sfGFP |
| FP2 | `LEDD` 523 | `nm550` / `nm583` | mYFP |
| FP3 | `LEDH` 600 | `nm620` / `nm670` | mCherry |

Exact commands in the runbook §7.4. Configure the red arm **manually** rather than trusting
`recommend_fp_settings`: mCherry's strongest *raw* cell is likely `ex550→nm620`, which sits on
the leak ridge (`LEDI` 550 has a 105 nm FWHM, so its red tail bleeds into `nm583`/`nm620` and
scales with turbidity), while the trustworthy readout is `ex600→nm670`. Gain matters little
here — the *scan* EEMs are the primary data (§8) and they auto-range; the logged channels are a
continuous cross-check.

## 8. Capture — what data actually matters

**Take the EEM from the scan route, not the FP CSV columns.** The CSV stores emit only as an
emit/base *ratio*, which is exactly what cannot be subtracted (raw emit + DARK count logging is
still an open TODO). The scan matrix holds gain-normalized counts and lands in
`sysData[M]['FluorescenceScan']['matrix']`.

**Gotcha:** `/getSysdata/` returns only the *current UI device*, so switch devices between grabs.

```bash
# Once, after cabling the extra reactors:
ssh ChiBio 'curl -s -X POST http://192.168.7.2:5000/scanDevices/all'; sleep 15
ssh ChiBio 'curl -s http://192.168.7.2:5000/getSysdata/ | python3 -c "import sys,json;print(json.load(sys.stdin)[\"presentDevices\"])"'

# At each ladder point, in the interleaved order from §6:
for M in M0 M1 M2 M3 M4; do   # numerical order is already interleaved
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/FluorescenceScan/$M/full"
  sleep 120   # watch the panel/terminal for completion rather than trusting the sleep
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/changeDevice/$M"
  ssh ChiBio "curl -s http://192.168.7.2:5000/getSysdata/" > eem_${M}_OD<actual>.json
done
```

Archive each EEM named with the reactor **and its measured OD at scan time**. Archive the CSVs
and the `_meta.json` / `_events.json` sidecars at the end of each run.

## 9. Pre-flight reminders

- **Cable M2–M4, then `/scanDevices/all`, then verify `presentDevices`** before any
  measurement. Never skip this — measuring an absent reactor takes the server down and trips the
  hardware cutoff on the running ones.
- **`OD0.target` is at the 65000 default** (confirmed 2026-07-20) — the stale placeholder, not a
  blank. **Blank every reactor individually** against sterile media before inoculation, and
  re-blank after any server restart (the blank lives in RAM only).
- Stop the server **only** with `./cb-stop.sh`.
- Thermostat 37 °C ON and stir ON for all inoculated reactors. Set the sterile blank reactor to
  the same temperature and stir so its optical conditions match.
- The sterile-media scan must happen **before** inoculation — it is not recoverable afterwards.

## 10. Acceptance criteria

1. **Run 0:** reactor-to-reactor EEM offsets are stable and reproducible across the ladder, and
   σ_device is small relative to the FP cell magnitudes from §1. If not, cross-reactor
   subtraction is not viable and the design must move to sequential same-reactor controls.
2. **Run 1, primary:** after subtracting the density-matched WT EEM, the mCherry cell
   (`ex600→nm670`) emerges clearly above background in TB205. This is the method anchor — if
   subtraction fails here it fails everywhere. With one FP arm per fluorophore, the error bar
   comes from the **WT pair** (σ of the subtrahend) and σ_device from Run 0, not from an FP
   replicate — so criterion 1 has to hold before criterion 2 means anything.
3. **Run 1:** subtracted signal vs OD is linear with a near-zero intercept across the ladder.
4. **Spectral spread:** same test for sfGFP (`ex457→nm510` or `nm550`). sfGFP is expected to be
   marginal on V2, which lacks a ~488 nm channel; a negative there is an informative bound on
   the hardware, not a failure of the protocol. mYFP (`ex523→nm550`) is deferred to the
   follow-up run — the FP2 channel is configured here so that run is directly comparable.

Only if 1–3 hold does it make sense to build matched-control subtraction as a first-class FP mode
and re-tune `recommend_fp_settings` against subtracted EEMs.
