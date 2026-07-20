# Bench runbook — matched non-fluorescent control experiment

Executable protocol. The *why* behind each choice is in
[`fluorescence-control-prep-plan.md`](fluorescence-control-prep-plan.md) — this file is what you
follow at the bench.

**Run 0** (WT in every reactor, ~½ day) and **Run 1** (the real experiment, ~1 day) use the
identical procedure below. The only difference is what you inoculate: Run 0 puts the same WT
culture in all six, Run 1 uses the strain assignment in §1. **Do Run 0 first** — it measures the
reactor-to-reactor offset that Run 1's subtraction depends on.

---

## ⚠ No pumps, capped vials — vent them

Batch mode needs no pumps, reservoir, or waste line, so the missing tubing costs you nothing
structurally. **A sealed vial, though, attacks this specific measurement from both sides.**

- **FP chromophore maturation requires molecular O₂** — for sfGFP, mYFP and mCherry alike, and
  mCherry's maturation is the slowest of the three. An O₂-starved culture makes FP
  protein that hasn't matured into a fluorophore — less of exactly the signal you're hunting.
- **Cellular autofluorescence rises when O₂ runs out.** The dominant autofluorophores are
  NAD(P)H and flavins, and their fluorescence tracks redox state. Flavins sit right in your
  measurement window (ex ~450, em ~525–535 → `LEDB 457` → `nm510`/`nm550`). So the background
  grows while the signal shrinks — the worst possible direction.

Chi.Bio has **no dissolved-oxygen sensing**, so none of this is visible in the data. Mitigate it
physically:

1. **Do not seal the vials — parafilm included.** Closure options, best first. Anything on this
   list works; the one thing that doesn't is an airtight seal.

   | Closure | Verdict |
   |---|---|
   | **0.22 µm hydrophobic PTFE** syringe filter on a lid port | Best — sterile barrier *and* free gas exchange. **PTFE specifically**: a hydrophilic membrane (PES, cellulose acetate) wets out from condensation or stir splash, and a wetted membrane really does become a barrier. That failure mode is the one legitimate reason to distrust a filter vent — it's avoided by choosing the hydrophobic grade and mounting it where condensate can't pool. |
   | **Micropore / surgical tape** over the open ports | Excellent, cheap, standard practice |
   | **Sterile cotton-wool or foam plug** | Classic breathable microbiology closure |
   | **Parafilm, perforated** with several needle holes | Acceptable fallback if it's what you have |
   | ~~Parafilm, intact~~ | **No — see the transport comparison below** |

   **Why a filter beats a film by ~1000×, despite "restricting" flow.** The two closures move O₂
   by different physics, and no bulk flow is involved in either. Through parafilm, O₂ must
   *dissolve into the wax* and diffuse through a solid — solution-diffusion, with a polymer
   diffusivity around 10⁻⁷ cm²/s and a solubility penalty on top. Through a filter (or tape, or
   a cotton plug) O₂ diffuses through **air-filled pores**, where D ≈ 0.2 cm²/s — about six
   orders of magnitude higher, with no solubility term. Against a demand of **58 µmol/h** at
   OD 0.6:

   | Closure | O₂ delivered |
   |---|---|
   | Parafilm, as supplied | ~0.2 µmol/h |
   | Parafilm, stretched thin | ~0.5 µmol/h |
   | Parafilm, stretched + 25× generous permeability | ~11 µmol/h |
   | 0.22 µm filter, deliberately pessimistic path | ~300 µmol/h |
   | 0.22 µm filter, realistic housing path | ~6000 µmol/h |

   Even granting parafilm a 25× permeability benefit of the doubt it still falls ~5× short,
   while a pessimistically-modelled filter clears demand 5× over. The filter's pressure rating
   describes *liquid* flow under a pump; it says nothing about gas exchange, which needs no
   pressure gradient at all — consumption inside the vial maintains the concentration gradient,
   and the vial never has to "inhale". This is exactly why 0.2 µm vent filters are the standard
   closure on fermenter headspaces.

   **The numbers, for a 20 mL culture in ~10 mL of headspace:** reaching OD 0.6 requires about
   **150 µmol O₂** (≈1 g O₂ per g dry cell weight, aerobic growth on glucose). Sealed headspace
   air holds about **83 µmol**, plus ~4 µmol dissolved. That is **roughly half of what the run
   needs, and it runs out at about OD 0.35** — between L1 and your primary L2 point.

   This is worse than a uniform loss of sensitivity, and it is *not* rescued by the matched
   control. O₂ depletion is progressive, so FP chromophore maturation gets worse as OD rises —
   a systematic error **correlated with density**, which is the exact axis acceptance criterion 3
   tests. A sealed run would bend the subtracted-signal-vs-OD line and you would wrongly conclude
   that matched-control subtraction isn't linear, for reasons having nothing to do with the
   method. The control can't correct it because the control has no FP to mature.

   If the worry driving the parafilm is contamination or evaporation: an 8 h run at 37 °C from a
   fresh colony in sterile media is low risk, air drawn through a 0.22 µm filter or cotton plug
   carries none, and evaporation through a small vent over 8 h is a few percent and common-mode
   across all seven reactors.
2. **Run 20 mL, not 25 mL.** That's Chi.Bio's own standard working volume and the extra
   headspace plus surface-to-volume meaningfully improves gas exchange in a stirred vial.
3. **Stir on, every reactor**, including the sterile blank.

**Why the experiment still works:** all seven vials are identically configured — same volume,
same vent, same stir — so O₂ status is *common-mode* and subtracts out along with the rest of
the background. That's the whole point of a matched control. What you lose is absolute
sensitivity, which makes a dim FP a harder call. Hence the vent.

Minor and acceptable: some evaporation over ~8 h at 37 °C through a vent (slightly inflates OD,
common-mode across reactors), and a little acetate from partially fermentative metabolism —
M9's phosphate buffers it and 0.2% glucose caps how much acid is available.

---

## 0. Strains — verified isogenic, control confirmed

All three FP strains are Addgene deposits from the Bergmiller/Guet labs, and they are **isogenic
apart from the fluorophore itself**:

| Strain | Addgene | Genotype | FP |
|---|---|---|---|
| **TB204** | [230033](https://www.addgene.org/230033/) | `MG1655 attP21::PR-sfGFP::frt` | monomeric **sfGFP** |
| **TB201** | [230031](https://www.addgene.org/230031/) | `MG1655 attP21::PR-mYFP::frt` | monomeric **mYFP** |
| **TB205** | [230034](https://www.addgene.org/230034/) | `MG1655 attP21::PR-mCherry::frt` | **mCherry** |
| **WT control** | — | `MG1655`, unmodified | none |

Same parental background, same integration site (`attP21`), same promoter (`PR`), single
chromosomal copy, **no antibiotic resistance in any of them**. Three consequences:

1. **Plain MG1655 is the correct matched control** — there is no plasmid, marker, or burden to
   match, so no empty-vector strain is needed. This was the open question; it's settled.
2. **No antibiotics anywhere**, which keeps the medium identical across all reactors — the
   condition matched-control subtraction depends on.
3. **Cross-fluorophore comparison is meaningful.** Because promoter, copy number, and locus are
   matched, differences between the three arms reflect *fluorophore and instrument*, not
   expression level. That turns this into a genuine test of which FP this hardware can actually
   quantify.

---

## 1. Reactor assignment

Cable **M0–M6** (seven). Leave M7 unconnected — it's the spare, and it keeps the scan window
short. The strain layout below is chosen so that **scanning in plain numerical order M0 → M6 is
already correctly interleaved**: every FP reactor is one or two positions from a control, so the
nearest-in-time control is never more than ~3 min away.

| Slot | Run 0 | Run 1 | Role |
|---|---|---|---|
| **M0** | WT | **WT-a** (MG1655) | Control |
| **M1** | WT | **TB205-a** (mCherry) | FP arm — best-served on V2 |
| **M2** | WT | **TB204** (sfGFP) | FP arm — worst case on V2 |
| **M3** | WT | **STERILE — never inoculated** | Instrument/tube floor |
| **M4** | WT | **WT-b** (MG1655) | Control replicate |
| **M5** | WT | **TB205-b** (mCherry) | FP replicate |
| **M6** | WT | **TB201** (mYFP) | FP arm — intermediate |
| M7 | — | — | Not connected |

**Why the replicates land where they do.** The control is the subtrahend in every subtraction,
so its noise propagates into every result — it gets n=2. mCherry gets the other n=2 because it
is the arm most likely to give a clean positive (§7.4), making it your method-validation anchor:
if subtraction doesn't work there, it won't work anywhere. sfGFP and mYFP run at n=1 to span the
spectrum. Six cultures plus the sterile blank keeps the reactor count at seven and the scan
window near 10 min.

In Run 0, M3 stays sterile too — it's your floor in both runs.

---

## 2. Consumables and equipment

| Item | Qty | Note |
|---|---|---|
| Chi.Bio reactor vials + caps | 7 | **20 mL working volume** (see the venting callout above) |
| **0.22 µm syringe filters — vents** | **7** | **One per vial. Not optional: no pumps means the lid is the only gas exchange.** |
| Magnetic stir bars | 7 | Standard, one per vial |
| Glycerol stocks | 4 | MG1655 WT, TB204 (sfGFP), TB201 (mYFP), TB205 (mCherry) |
| Agar plates | 4 | For streaking; LB is fine for plates (cells get washed) |
| Culture tubes for overnights | 4 | 50 mL tube or 25 mL flask, 5 mL culture each |
| M9 + 0.2% glucose | **500 mL** | One batch, one bottle — see §3 |
| 0.22 µm syringe filters | 2–3 | Additionally, for filter-sterilizing glucose and Mg/Ca stocks |
| Microcentrifuge tubes | ~6 | Washing the inocula |
| Cuvettes | ~10 | Benchtop OD checks |
| 70% ethanol | — | Surface/lid sterilization |

**Media volume budget:** 7 reactors × 20 mL = 140 mL, overnights 4 × 5 mL = 20 mL, washing
~30 mL, benchtop dilutions and spillage ~50 mL. That's ~235 mL — **make 500 mL** so you are never
tempted to top up from a second batch. One batch, one bottle, for every reactor including the
sterile blank.

---

## 3. Media — M9 + 0.2% glucose, 500 mL

**5× M9 salts** (per 1 L, autoclave): Na₂HPO₄·7H₂O 64 g (or 33.9 g anhydrous Na₂HPO₄),
KH₂PO₄ 15 g, NaCl 2.5 g, NH₄Cl 5 g.

**Working medium, 500 mL** — combine *after* autoclaving, into cooled salts:

| Component | Volume | Final |
|---|---|---|
| 5× M9 salts (autoclaved) | 100 mL | 1× |
| Sterile H₂O | ~394 mL | — |
| 1 M MgSO₄ (sterile) | 1 mL | 2 mM |
| 1 M CaCl₂ (sterile) | 50 µL | 0.1 mM |
| 20% (w/v) glucose (0.22 µm filtered) | 5 mL | **0.2%** |

**Order matters.** Add Mg²⁺ and Ca²⁺ to the *diluted* salts, never to the 5× concentrate — they
precipitate with concentrated phosphate. Never autoclave glucose together with the ammonium
salts (Maillard browning, and browned media fluoresces, which is exactly what you're trying to
measure). Filter-sterilize the glucose separately.

MG1655 is prototrophic, so no thiamine or amino acid supplements are needed. **No antibiotics in
anything** — the FPs are single chromosomal copies needing no selection, and the medium must be
identical across all reactors.

---

## 4. Day −2 — plates

Streak all **four** stocks onto separate plates — MG1655 WT, TB204 (sfGFP), TB201 (mYFP),
TB205 (mCherry). 37 °C overnight, then 4 °C until use.

## 5. Day −1 — overnights, media, hardware

**Evening:**
1. Pick a **single colony** per strain into **5 mL M9 + 0.2% glucose**. 37 °C, shaking, ~16 h.
   Use M9, **not LB** — LB is strongly autofluorescent and the carryover contaminates the exact
   background you're characterizing, and M9-adapted cells skip the transfer lag.
   *One flask per strain* — where a strain occupies two reactors (WT and TB205), split that
   single flask between them, so "replicate" measures the instrument rather than your pipetting.
2. Make the 500 mL of media (§3). Leave at room temperature or 4 °C.
3. Clean and autoclave the 7 vials + stir bars. Check your lid material first — if the caps
   aren't autoclavable, 70% ethanol and air-dry in the hood instead.

**Also on Day −1: cable the reactors and restart the server** (§6). Do not leave this for the
morning; it's the step most likely to surprise you.

---

## 6. Cabling M2–M6 — the step that will silently corrupt your data if skipped

**After physically connecting the new reactors you must restart the server.** `/scanDevices/all`
sets the `present` flag but **does not call `initialise()`**, and `initialise()` is where the
LED hardware version is detected. The default `Version.LED` is **1** (`chibio_state.py:15`), your
boards are **V2**, and `excitation_leds()` branches on it:

- V1 set: `LEDA 395 · LEDB 457 · LEDC 500 · LEDD 523 · LEDE 595 · LEDF 623`
- V2 set: `LEDB 457 · LEDC 500 · LEDD 523 · **LEDI 550** · **LEDH 600** · LEDF 623`

A newly cabled reactor left at the default would be scanned with the V1 list: `LEDA` and `LEDE`
don't exist on a V2 board and are **silent no-ops, not errors**, while `LEDI 550` and `LEDH 600`
never get driven at all. You'd get a partly-empty EEM that is not comparable to M0/M1 — and
`LEDI 550` is precisely the autofluorescence ridge you are trying to characterize.

```bash
# 1. Power down, cable M2-M6 physically.
# 2. Restart the server so initialiseAll() runs initialise() on every reactor:
ssh ChiBio 'cd /root/chibio && ./cb-stop.sh stop 5000'     # cb-stop.sh ONLY — never kill/pkill
ssh ChiBio 'cd /root/chibio && ./cb.sh'
sleep 30

# 3. Presence scan, then VERIFY. Never measure a reactor that isn't confirmed present:
ssh ChiBio 'curl -s -X POST http://192.168.7.2:5000/scanDevices/all'; sleep 15

# 4. Confirm all seven are present AND all report LED version 2:
for M in M0 M1 M2 M3 M4 M5 M6; do
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/changeDevice/$M >/dev/null; \
    curl -s http://192.168.7.2:5000/getSysdata/" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('$M', 'present=', d['presentDevices']['$M'], 'LED=', d['Version']['LED'])"
done
# Expect: present=1 and LED=2 on all seven. Anything else -> stop and fix before proceeding.
```

Measuring a reactor that is absent drives `I2CCom` into `os._exit(4)` and trips the hardware
watchdog on the *running* reactors. This verification is not optional.

---

## 7. Day 0 — the run

Clock times assume an 08:00 start; **trigger the ladder scans off measured OD, not the clock.**

| Time | Step |
|---|---|
| 08:00 | Fill all 7 reactors with **19 mL** media. Fit the **0.22 µm vent filters**. Thermostat 37 °C ON, stir ON, on **all seven** (M3 included — its optics must match). |
| 08:45 | Temperature equilibrated. **Blank every reactor** (§7.1). |
| 09:00 | **Sterile EEM scan, all 7** (§7.3, ~10 min). This is your OD-0 ladder point and is unrecoverable once you inoculate. |
| 09:15 | Wash and normalize inocula (§7.2). Set FP3 config (§7.4). |
| 09:30 | **Inoculate M0, M1, M2, M4, M5, M6** with 1 mL each → 20 mL at OD ≈ 0.02. **M3 gets nothing.** Start the experiment on all 7 for CSV logging. |
| ~13:00 | **L1** — first reactor reaches OD 0.2 → scan all 7 |
| ~14:10 | **L2 — OD 0.4, the primary point** → scan all 7 |
| ~15:00 | **L3** — OD 0.6 → scan all 7. **Stop here.** |
| ~15:30 | Stop experiment, archive everything (§8). |

**Trigger every scan off measured OD, not the clock.** The clock column assumes μ ≈ 0.65/h, but
a vented-but-unaerated stirred vial will run slower than that, and there's up to ~1 h of lag
from the stationary-phase inoculum on top. Both are common-mode across reactors, so they shift
the schedule without distorting the comparison — just don't let a wall clock start a scan.

**Ladder is 0.2 / 0.4 / 0.6, and 0.4 is the one that matters.** The Chi.Bio paper's own
fluorescence procedure holds cells at **OD 0.4** for FP work — that's the density their settings
were characterized at, so it's your best-supported comparison point. The top of the ladder came
down from 0.8 to 0.6 for two reasons: without aeration you may struggle to reach 0.8 in a
sensible time, and 0.8 was already edging toward the regime where the FP CLEAR base broke 60000
on 27–40% of cycles and the saturation guard NaNs the reading out. Three points still test
linearity; **do not chase plateau.**

Worth knowing, from the same source: the Chi.Bio authors subtract a **WT-no-plasmid baseline**
for their fluorescence work. The design you're running here is what the instrument's own authors
do — you're closing a gap in this fork, not inventing a method.

### 7.1 Blank every reactor

The blank is per-reactor and lives in RAM only — it resets to the stale 65000 default on every
server restart, so blank *after* the restart in §6, and re-blank if you restart again.

With sterile media in the vial at 37 °C and **stir ON** (unstirred laser reads vary ~15%,
stirred <3%), take ~5 `MeasureOD` reads per reactor, average the reported `OD0['raw']`, then:

```bash
# knownOD=0 sets OD0.target = the raw you pass, i.e. zero-at-blank.
ssh ChiBio 'curl -s -X POST http://192.168.7.2:5000/CalibrateOD/OD0/M0/<mean_raw>/0'
# ...repeat per reactor with that reactor's own mean. Then verify each is no longer 65000.
```

### 7.2 Inocula

Pellet each overnight, **wash once in fresh M9**, resuspend (removes spent-media fluorophores).
Normalize all four to the **same OD** on the benchtop spectrophotometer, then put 1 mL into
19 mL — from an OD ~0.45 washed stock that gives OD ≈ 0.022 in the 20 mL reactor. Split the WT
and TB205 flasks across their two slots each.

### 7.3 Scan — capture the EEM, not the CSV

The CSV stores emit only as an emit/base **ratio**, which is exactly what cannot be subtracted.
The scan matrix holds gain-normalized counts. Note `/getSysdata/` returns **only the current UI
device**, hence the `changeDevice` before each grab.

```bash
# Record each reactor's OD immediately before its own scan; name the file with the ACTUAL OD.
for M in M0 M1 M2 M3 M4 M5 M6; do          # numerical order = correctly interleaved
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/FluorescenceScan/$M/full"
  sleep 120    # ~1-1.5 min/reactor; watch the UI terminal for completion rather than trusting this
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/changeDevice/$M >/dev/null"
  ssh ChiBio "curl -s http://192.168.7.2:5000/getSysdata/" > eem_${M}_L1_OD<actual>.json
done
```

Scans are strictly serial — one I2C bus, one global lock — so a ladder point is ~10 min for
seven reactors, during which cultures grow ~11%. That's why you record per-reactor OD and
subtract against the nearest-in-time control.

### 7.4 FP logging channel

You have three FP slots, so use all three — one per fluorophore — and set them **identically on
all seven reactors**, controls and sterile blank included. Every reactor then logs all three
channels, and each FP arm's channel has a directly comparable control channel. Each slot captures
**two** emission bands (`Emit1`/`Emit2`), which is enough to cover both candidate readouts per FP.

| Slot | Excite | Emit1 / Emit2 | For |
|---|---|---|---|
| **FP1** | `LEDB` 457 | `nm510` / `nm550` | sfGFP |
| **FP2** | `LEDD` 523 | `nm550` / `nm583` | mYFP |
| **FP3** | `LEDH` 600 | `nm620` / `nm670` | mCherry |

```bash
for M in M0 M1 M2 M3 M4 M5 M6; do
  ssh ChiBio "curl -s -X POST http://192.168.7.2:5000/changeDevice/$M >/dev/null
    curl -s -X POST http://192.168.7.2:5000/SetFPMeasurement/FP1/LEDB/CLEAR/nm510/nm550/x10
    curl -s -X POST http://192.168.7.2:5000/SetFPMeasurement/FP2/LEDD/CLEAR/nm550/nm583/x10
    curl -s -X POST http://192.168.7.2:5000/SetFPMeasurement/FP3/LEDH/CLEAR/nm620/nm670/x10"
done
```

**Why mCherry is the best-served fluorophore on this board, and where the trap is.** V2 carries
`LEDH` at 600 nm — essentially the **595 nm the Chi.Bio paper itself specifies for RFP**, whose
documented config is *595 nm @0.1 power, ×512 gain, Clear base, **670 nm emit***. Reading mCherry
at `nm670` also escapes the background ridge: `LEDI` 550 has a **105 nm FWHM** (`chibio_state.py:26`),
so its red tail leaks straight through into `nm583`/`nm620` and scales with turbidity — that is
the mechanism behind the `ex550→nm583/620` ridge that defeated every previous scan.

**The trap:** mCherry's strongest *raw* cell will most likely be `ex550→nm620`, sitting right on
that ridge, and `recommend_fp_settings` maximizes signal — so it will probably steer you there.
Configure the red arm manually as above and treat any `ex550` recommendation with suspicion.

Gain: the **scan EEMs are the primary data and they auto-range**, so don't agonize here — the
logged channels are a continuous cross-check. Start at ×10 and watch the CLEAR base; the paper's
×512 assumes 0.1 LED power and OD 0.4. The near-saturation guard (`valid=0` → NaN at base ≥60000)
is your safety net either way.

---

## 8. Archive

```bash
mkdir -p ~/chibio-control-run/{run0,run1}
scp ChiBio:'/root/chibio/*_data.csv'     ~/chibio-control-run/run1/
scp ChiBio:'/root/chibio/*_meta.json'    ~/chibio-control-run/run1/
scp ChiBio:'/root/chibio/*_events.json'  ~/chibio-control-run/run1/
# plus every eem_M*_L*_OD*.json from §7.3
```

Keep a paper log of the **measured OD of each reactor at each scan** — it is the key you need to
density-match, and it is not reliably recoverable afterwards.

---

## 9. Watch-outs

- **`cb-stop.sh` only.** Never `kill`, `pkill`, or kill a PID from `ss -ltnp` — that wedged the
  board on 2026-07-17 and needed a physical power-cycle.
- **Verify `present=1` and `LED=2` on all seven before any measurement** (§6).
- **Blank after every server restart** — it's RAM-only.
- **The sterile scan must precede inoculation.** Not recoverable afterwards.
- **M3 never gets cells.** Label it physically so a tired hand at 09:30 doesn't inoculate it.
- **Vent every vial through a 0.22 µm filter** — a sealed vial suppresses FP maturation *and*
  raises autofluorescence. Same vial, same volume, same vent on all seven.
- **Stop at OD 0.6**, don't run to plateau. OD 0.4 is the primary point.
