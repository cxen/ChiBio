# Invariants

Rules that hold on this rig, each one learned by breaking something. **Read before touching
hardware, before writing a watcher script, and before trusting a number.**

Format: the rule, then *why* — because a rule without its mechanism gets "improved" away.
Dates mark when the rig taught us. `CLAUDE.md` holds architecture; this holds hard-won
operational constraints. Where a claim is untested, it says so.

---

## 1. Physical handling

| If you do this | This happens |
|---|---|
| Handle reactors/vials while the server is **live** | I²C transient → `I2CCom` retries → watchdog `os._exit(4)` → **the run dies**. 2026-08-12 11:22. |
| Leave one reactor faulty but **connected** | It wedges the **entire shared bus**. Every other reactor dies with it. |
| **Disconnect** a reactor entirely | Handled gracefully — M5–M7 have been absent throughout without issue. |
| Move a vial vertically in its holder | Changes **thermal contact** *and* **stir-bar coupling**. Both persist until moved again. |
| Run the thermostat with an **empty holder** | `Thermostat` regulates on `ThermometerIR`, which points at the vial contents. With no liquid it drives the heater against nothing. **Always stop the thermostat before removing vials.** |
| Reseat a vial mid-run | Produces large single-sample IR excursions that look exactly like sensor faults. 2026-08-11 19:51–19:52 — three of them, all benign. |

**Do all vial handling with the server stopped.** This costs a restart (and therefore a re-blank);
a wedged bus costs the run.

**A faulty reactor is worse than an absent one.** If a reactor misbehaves, unplug it rather than
leaving it in.

### Recipe: localising a bus wedge to a physical part

A wedged bus names one reactor in the log but that only identifies a *branch*, not a part. The
server refusing to boot is a **usable diagnostic instrument** — each attempt is a clean binary
test. Run these in order and stop at the first informative result. Server **stopped** for every
physical change.

| Step | Change | If it fails | If it boots |
|---|---|---|---|
| 1 | Reseat the named reactor's connector | not seating → step 2 | seating was the fault |
| 2 | Swap its cable for a known-good one | not the cable → step 3 | the cable is faulty |
| 3 | **Unplug it entirely** | fault is elsewhere — re-read the log | fault is confined to that branch → step 4 |
| 4 | Move that reactor to a **different controller port** | **fault follows the reactor** → the reactor unit is faulty | fault stayed with the port → the controller channel is faulty |

Step 4 is the one that separates reactor from controller, and it is the only step that does.
Worked 2026-08-12: M4 failed on its own port, failed reseated, failed on the pump cable, vanished
when unplugged (clean boot, self-test 16/16), and **failed as M7 when moved to port T7** — so the
reactor unit, not the cable or the channel. Total elapsed ~40 min, all of it decisive.

Do not skip step 3. A clean boot with the suspect removed is what proves the rest of the rig is
healthy, and it gives you a working rig to fall back to if the diagnosis stalls.

---

## 2. Diagnostics that lie

These produced confident, wrong conclusions. Every one cost time.

**Never read `P9_19`/`P9_20` as GPIO.** They are I²C2's SCL and SDA.
`Adafruit_BBIO.GPIO.setup()` **remuxes the pin away from the I²C peripheral**, so the measurement
breaks the thing being measured, and the reading is meaningless anyway. Recovery is a reboot
(restores the device-tree default). 2026-08-12 — produced a false "both lines stuck low"
diagnosis.

**`i2cdetect` before the server starts is always empty.** The watchdog pulses `P8_11` into a
D-latch that gates the **reactor electronics**, and `setup_watchdog()` is what drives the mux
RESET (`P8_15`) high. No server ⇒ no watchdog ⇒ electronics unpowered ⇒ nothing on the bus.
**An empty scan pre-boot is normal, not a fault.** The only real test is booting the server.

**`OD['current']` is stale until the next measurement.** After `CalibrateOD` it still shows the
value computed against the *old* blank. Wait a cycle before reading, or recompute from
`OD0['raw']` and the new target.

**A frozen experiment thread is invisible.** `OD['current']` holds its last value — plausible,
stable, **low `od_spread`**, no `valid=0`. M3 sat at a frozen 1.681 for 90 minutes and read as
live data. **The only reliable liveness check is `Experiment['cycles']` advancing.**

**`valid=1` does not mean the number is good.** It means the I²C read succeeded. A laser or LED
switched off by a racing thread yields `raw=0, valid=1`.

---

## 3. Watcher and process-management scripts

**Never `pkill -f <pattern>` over ssh.** The remote `bash -c` command string *contains the
pattern*, so pkill matches and kills its own shell. It returns exit 255 with the target
untouched — and the failure is silent until the next command. The bracket trick (`[t]herm`)
saves `grep` but is not reliable for `pkill`/`pgrep`.

**Everything that scans processes self-matches**, including `ps | grep`, `pgrep -f`, and your own
`/proc` walker whose source contains the search string as a literal. Two false "process is
running" reports came from this in one session.

**The safe kill pattern:**

```python
import os, signal
me = os.getpid()
for p in os.listdir("/proc"):
    if not p.isdigit() or int(p) == me:            # self-exclusion is mandatory
        continue
    try:
        c = open("/proc/%s/cmdline" % p).read().replace("\0", " ")
    except Exception:
        continue
    if c.strip().startswith("python3 /tmp/supervisor.py"):   # exact, anchored
        os.kill(int(p), signal.SIGTERM)
```

Anchor with `startswith` on the exact command, not a substring search.

**Never kill pids harvested from an unfiltered `ss -ltnp`.** It lists systemd (pid 1), sshd,
nginx, dnsmasq and node as well as gunicorn. Doing so once SIGTERM'd every daemon including
`kill 1` and needed a physical power-cycle. **Stop the server only with `./cb-stop.sh stop 5000`**,
which validates `/proc/<pid>/comm == "gunicorn"` and refuses pid 1.

**Detaching a long-runner over ssh:**

```bash
nohup python3 /tmp/supervisor.py >/tmp/supervisor.log 2>&1 </dev/null &
sleep 5     # let it start before the ssh session tears down
```

Then **verify it survived**: its `ppid` must be `1`. A `pkill` earlier in the same command line
can kill the shell before `nohup` ever runs — that happened, and the launch silently did nothing.

**Waiters must be bounded and must watch for failure, not just success.** A watcher that greps
only for the success marker stays silent through a crash. Include the failure signatures in the
same alternation. An ssh-based waiter returning **exit 255 means the connection dropped**, not
that the job failed.

**Don't poll for something the harness will tell you about.** Long fallbacks, not tight loops.

---

## 4. Single-owner rule

**`/getSysdata/` returns only the current UI device**, and `/changeDevice/<M>` mutates one global.
**Two processes that both select and read will read each other's reactor.** There is no
per-request scoping to fall back on.

This corrupted a blanking pass on 2026-08-11: a thermal guard sweeping all five every 60 s kept
reselecting M4, so the blanking script recorded **M4's stale raw (10388) as M0's and M1's**, five
times identically, and applied it. Nothing errored; `valid` was 1 throughout.

- **Exactly one process** may talk to the server. Fold every background duty — guard, blanking,
  scans, monitoring — into a **single supervisor**.
- After `/changeDevice/<M>`, **assert** `getSysdata()['UIDevice'] == M` before trusting the read.
- Two identical consecutive values are a staleness smell but **not proof** — a quiet sensor
  legitimately repeats an integer. M3 blanked at CV 0.078% with two identical reads and was
  wrongly rejected by an over-strict freshness check.

---

## 5. Server and state

**All experiment state is RAM-only.** A gunicorn worker restart resets blanks to the 65000
default, clears FP config, and zeroes `cycles`. **The master survives and the port stays open, so
from outside nothing looks wrong.** Two occurrences: 2026-08-11 20:12:57 (default 30 s timeout)
and 2026-08-12 09:30:52 (at `--timeout 300`, **still unexplained**).

- `cb.sh` runs `--timeout 300 --graceful-timeout 60`. Do not remove.
- Per-cycle bus work scales as *reactors × (OD replicates + FP slots × FP replicates)*. Five
  reactors × 3 FP slots is ~7× the 2024-07 configuration. **Assume the worker timeout, not the
  cycle time, is the binding constraint** — an overrunning cycle is benign, a killed worker is not.
- **Record every blank.** After a restart, restore with `POST /CalibrateOD/OD0/<M>/<raw>/0` using
  the logged value rather than re-blanking against a grown culture.
- **Auto-recovery must distinguish "one thread died" from "the worker was wiped."** Ours did not,
  and on 2026-08-12 09:36 it restarted all five into fresh, unblanked CSVs. Check whether
  `cycles` reset to 0 across *all* reactors at once; if so, restore blanks first or refuse and alert.

**Measurement routes are fire-and-forget** (`run_background`) and settle in ~1.6 s. Firing faster
lets sibling threads switch the laser off mid-read → `raw=0, valid=1`. **Space reads ≥5 s**, or
poll until the value changes.

**A `FluorescenceScan` collides with the experiment's own cycle on the same reactor.** The global
lock serializes individual I²C transactions but *not* on→read→off sequences. Two symptoms: one
corrupted OD row per reactor per scan (`raw=0`, `spread`~1.1, **unflagged**), and — at least once —
**the experiment thread dying outright** (M3, 2026-08-11 22:22:17), which also left stir off.

---

## 6. Stirring

**`runExperiment` stops and restarts the stirrer every cycle** (`chibio_experiment.py:324` /
`:407`), and `SetOutput`'s Stir branch always **hard-starts at full power for 1.5 s** from rest
(`app.py:553`). **There is no gentle-ramp path anywhere in the API** — even
`set_output_target_sync` re-triggers the full kick on any target change (`app.py:514`).

Over a 13 h run that is **~780 restarts per reactor**. **This is protective, not hazardous** — see
the three states below. An earlier version of this file called the per-cycle restart a risk;
that was wrong.

**The three stir states, from bench observation 2026-08-12** (operator, by eye and ear — more
informative than any log):

| State | Sound | Behaviour | Mixing |
|---|---|---|---|
| **Smooth** | silent | whirlpool visible | good |
| **Rough** | audible | more agitated, **a single layer of surface bubbles** (not foam) | vigorous; surface breaking, so if anything better gas transfer |
| **Clanking** | bar hitting glass | **bar does not rotate**, just jumps | **none — this is the failure** |

**Clanking is caused by seating a vial while the stirrer is running**, and is **fixed by pausing
and restarting the stirrer**, which lets the bar re-centre. So: **always load vials with stir
OFF**, and if a reactor clanks, toggle stir rather than touching the vial.

**M0's poor growth in Run 0 is UNEXPLAINED — do not adopt a mechanism for it yet.** It grew at
µ 0.404 against ~0.95 elsewhere, to a plateau of 1.52 against 2.94, and the cuvette cross-check
confirmed **genuinely fewer cells**, so it is not an optical artifact. Two mechanisms were
proposed on 2026-08-12 and both failed: "poor mixing" (M0 is the *vigorous* one) and "foam wets
the vent filter and blocks gas exchange" (the bubbles are a single surface layer, not foam, and
cannot reach the filter). Halving µ for *E. coli* in a stirred 20 mL vial at 37 °C is a large
effect that mixing state alone does not readily produce. Candidates not yet tested: residual
ethanol from vial wiping, an aliquoting difference in the medium, or something specific to that
vial. **Resolve it before trusting M0 with anything load-bearing.**

**Bar shape is not the variable.** Swapping M0's and M1's bars on 2026-08-12 left the behaviour
with **M0**, so it is the reactor's drive magnet, motor or holder geometry. Vertical sensitivity
(state changes when the tube is lifted through the field) points at the magnet-to-bar gap, i.e.
**seating depth**. Do not buy new stir bars to fix a per-reactor mixing problem without doing the
swap test first — it costs one minute and settles it.

**Consequences for data:** `od_spread` is a usable mixing proxy — the sterile M2 stayed below
0.01 for 782 consecutive cycles (no cells to suspend), while M0 exceeded 0.04 in **49%** of
cycles. High-spread fraction tracked the growth deficit (M0 49%/µ 0.40, M3 29%/µ 0.66,
M4 21%/µ 0.84, M1 8%/µ 0.78).

**Therefore: reactor-to-reactor growth differences are not a stable calibration.** They depend on
how each tube happens to sit and are re-rolled every cycle. Optical differences *are* stable;
mixing differences are not. **Fix mixing rather than calibrating around it.**

---

## 7. Measurement and data

**Blank under the conditions the run measures in.** `runExperiment` measures with **stir off after
a 5 s settle** and takes a 3× median. Manual `/MeasureOD/` reads are taken **with stir running** —
a different optical state. M1 read ~4000 stirred against ~15500 settled. Blank from the running
experiment's own values, in situ and at temperature.

**Plan FP gain for the density the run will *reach*, not its starting density.** At `x10` (512×)
the CLEAR base went from ~6–11k at inoculation to 34–60k in two hours; the 60000 guard NaN'd
**49% of M4's FP1 rows and 57% of M0's FP2**. **Autorange does not rescue this** — it only steps
down on an *exact* 65535, so the whole 60000–65534 band is lost. Dropping to `x6` (32×) took the
base to 3.5–8.5k and gave **0% NaN** thereafter. The emit/base **ratio is gain-invariant**, so a
mid-run gain change is safe for comparability and `SetFPMeasurement` logs it to the events sidecar.

**Raw FP emission is recoverable** even though only ratios are stored: `FP*_base` is logged as raw
counts and `FP*_gain_used` per row, so `emit_raw = emit_ratio × FP*_base`.

**Always filter `od_transmission_raw == 0`** — scan collisions, unflagged.

**Dilute above cuvette OD ~0.8.** Undiluted readings at 1.14 and 0.98 were compressed by 14% and
5%. Those two errors coincidentally tightened an agreement and produced a **false CV of 2.8%**
where the honest figure was 7.7%.

**Fit growth over ≥3 h.** A one-hour window plus an assumed inoculation offset gave t_d 29–36 min,
which is not physically possible in M9 + glucose. Three hours with a *measured* offset gave
**50–53 min**. Short windows are dominated by the additive offset.

**Anchor to biology, not to software t=0.** `Experiment['startTime']` is when logging began.
Record the inoculation wall-clock time separately (see `labnotes.md`).

---

## 8. Provenance

Never present a number without the caveat that limits it. Specific failures to avoid repeating,
all from 2026-08-11/12:

- Reporting CV 2.8% when nonlinearity had manufactured the agreement.
- Diagnosing "spurious IR sensor reads" when the user had been reseating tubes.
- Calling reactor-to-reactor variation a stable offset map before knowing mixing was a per-cycle
  lottery.
- Presenting a GPIO reading as evidence when taking the reading broke the pin's function.

**When a measurement and a physical explanation compete, get the physical one first.** The bench
observation ("the bar sticks until I move the tube") explained more in one sentence than several
hours of log analysis.
