# Monday runbook — deploy the FP saturation guard + set up the fluorescence control

Prepared 2026-07-18 (remote; controller must not be restarted until physically present).
Do this **on-device, physically present**, because it restarts the server (and the running
weekend experiment). Every command is copy-pasteable. Safety rails are called out inline.

**Golden rules (from the `device-deployment` memory — do not deviate):**
- **Stop the server ONLY with `./cb-stop.sh`.** Never `ss|kill`, `pkill`, or `kill` a PID
  from `ss -ltnp` — that wedged the board on 2026-07-17 and needed a physical power-cycle.
- **Staging first, then promote.** rsync to `/root/chibio-staging`, self-test there, only then
  rsync to `/root/chibio`.
- The **watchdog is NOT a hazard** when stopping gunicorn (it gates reactor electronics via a
  latch, not BeagleBone power — the board keeps its network the whole time).

---

## 0. What Monday is actually doing

The weekend run is glucose-limited batch (M9 + 0.2% glucose): it plateaued ~Saturday and has
been in stationary/starvation since — so by Monday **this run is effectively spent**, and the
natural move is to **end it, deploy the guard, and start a fresh experiment that includes a
non-fluorescent control** (Section 4, the unblock for real fluorescence quantification).

Two paths — pick one:
- **Path A (recommended): fresh start.** End the weekend run, deploy, start a new experiment.
  OD blanks are re-done against fresh media (you're present) — the saved blanks below are then
  just a fallback, not needed.
- **Path B (contingency): resume the current cultures.** If you want to keep M0/M1 going across
  the restart, you must restore the RAM-only state the restart wipes (Section 3.5): OD blanks,
  FP config, thermostat/stir, and re-start the turbidostat.

---

## 1. Pre-flight (before touching anything)

```bash
# From the Mac. Confirm reachability + that the server is alive.
ssh ChiBio 'uptime; ss -ltn | grep :5000 && echo "server UP" || echo "server DOWN"'

# Snapshot current live state for both reactors (so nothing is lost). Grab the CSVs too.
ssh ChiBio 'curl -s http://192.168.7.2:5000/getSysdata/ > /tmp/pre_deploy_M1.json'
scp ChiBio:'/root/chibio/*_data.csv' ~/chibio-weekend-data/   # archive the run's data
```

Confirm the Mac repo is at the intended commit (the guard is `0b43bd6`):
```bash
cd /Users/Constantinos/GitHub/ChiBio && git log --oneline -3
```

---

## 2. Off-device tests (already green, re-run to be sure)

```bash
cd /Users/Constantinos/GitHub/ChiBio
VENV=/private/tmp/claude-504/-Users-Constantinos-GitHub-ChiBio/fd914421-87fa-42ce-b547-db2d7b64e1a3/scratchpad/chibio-venv
# (or rebuild: python3 -m venv v && v/bin/pip install flask numpy smbus2 simplejson; VENV=v)
for t in test_fp_saturation test_import_smoke test_csv_equivalence test_metadata_sidecar \
         test_read_validity test_autorange test_replicate test_fluorescence; do
  CHIBIO_MOCK_HW=1 "$VENV/bin/python" $t.py || echo "FAIL $t"
done
# Expect: 8/8 pass (7 existing + the new guard test).
```

---

## 3. Deploy

### 3.1 End the weekend run cleanly (Path A) and stop the server
```bash
# If an experiment is running and you want its final CSV closed, stop the experiment in the UI
# first (optional). Then stop the server — cb-stop.sh ONLY:
ssh ChiBio 'cd /root/chibio && ./cb-stop.sh stop 5000'
ssh ChiBio 'ss -ltn | grep :5000 || echo "5000 free"'   # verify it actually stopped
```

### 3.2 rsync to staging (recreate it — it does NOT reliably persist)
```bash
ssh ChiBio 'mkdir -p /root/chibio-staging; git config --global --add safe.directory /root/chibio-staging'
rsync -az --delete --exclude='.DS_Store' --exclude='.chibio_token' --exclude='.claude' \
  --exclude='selftest-*.json' -e ssh \
  /Users/Constantinos/GitHub/ChiBio/ ChiBio:/root/chibio-staging/
```

### 3.3 Boot staging + self-test (I2C paths — you're present, so this is fine)
```bash
ssh ChiBio 'cd /root/chibio-staging && ./cb.sh'          # binds 0.0.0.0:5000
# In another shell, run the device self-test against the running staging server:
ssh ChiBio 'cd /root/chibio-staging && python3 device_selftest.py staging-guard'
# Expect 8/8 on M0/M1. Then stop staging:
ssh ChiBio 'cd /root/chibio-staging && ./cb-stop.sh stop 5000'
```

### 3.4 Promote to /root/chibio (include .git so the metadata git-hash stays accurate)
```bash
rsync -az --delete --exclude='.DS_Store' --exclude='.chibio_token' --exclude='.claude' \
  --exclude='selftest-*.json' -e ssh \
  /Users/Constantinos/GitHub/ChiBio/ ChiBio:/root/chibio/
ssh ChiBio 'cd /root/chibio && ./cb.sh'                  # launch the promoted server
```

### 3.5 Path B ONLY — restore the state the restart wiped
Skip this entirely on Path A (you'll blank fresh in Section 4). The restart resets
`OD0.target` to the 65000 default and clears FP config, thermostat/stir, and experiment state.

```bash
# Restore the exact OD blanks captured mid-run (knownOD=0 sets target = raw exactly):
ssh ChiBio 'curl -s -X POST http://192.168.7.2:5000/CalibrateOD/OD0/M0/15438.4/0'
ssh ChiBio 'curl -s -X POST http://192.168.7.2:5000/CalibrateOD/OD0/M1/15297.0/0'
# Verify:
ssh ChiBio 'curl -s http://192.168.7.2:5000/getSysdata/ | python3 -c "import sys,json;print(json.load(sys.stdin)[\"OD0\"][\"target\"])"'
```
Then re-set FP config (values as of the weekend run), thermostat, stir, and re-start the
turbidostat via the UI. **Current FP3 config for reference** (route
`/SetFPMeasurement/<item>/<Excite>/<Base>/<Emit1>/<Emit2>/<Gain>`):
- **M1 FP3 = `LEDD`(523) / base `CLEAR` / `nm550` / `nm583` / gain `x10`** (YFP-appropriate).
- M0 FP3 — check M0's own snapshot/CSV before restoring (GFP; likely `LEDB`(457)→`nm510`).
- Thermostat 37 °C ON, Stir 0.5 ON.

---

## 4. Verify the guard is live + set up the fluorescence control (Path A)

### 4.1 Confirm the saturation guard is active
The guard flags `valid=0` (→ NaN in CSV) when a FP CLEAR base ≥ 60000. Easiest check: once a
fresh dense-ish culture is running FP, look for NaN in the `FP*_emit1` CSV cells on cycles where
`FP*_base` ≥ 60000 (there should no longer be a numeric ratio logged there). Off-device this is
already proven; on-device it just needs one saturating read to exercise.

### 4.2 The non-fluorescent control — the real unblock
The onboard fluorescence can't be trusted for dim FPs because broad-spectrum LED leakage +
90°-geometry scatter produce a **concentration-dependent background** that the ratiometric
(emit÷Clear) method can't remove, and no single-reactor heuristic separates a dim FP from the
autofluorescence ridge (confirmed 2026-07-18: on the real M1 EEM the recommender picks the
`ex550→nm583` autofluorescence cell over true YFP `ex523→nm550`). The fix needs a
**matched non-fluorescent control**:

1. **Set up a control reactor** — same strain background, **no FP / no plasmid** (e.g. plain
   MG1655), same medium (M9 + 0.2% glucose), in a spare reactor slot. Grow alongside the FP
   reactors.
2. **Scan all three at matched density.** Autofluorescence + scatter scale with biomass, so the
   control must be at (or normalized to) the same OD as the FP reactors when scanned. Run
   `/FluorescenceScan/<M>/full` on each; capture the EEMs.
3. **Subtract.** FP-reactor EEM − control EEM (both gain-normalized, density-matched) = the real
   FP signal. The true FP cell (GFP ~`ex457→nm510`, YFP ~`ex523→nm550`) should emerge above the
   ridge after subtraction.
4. **Then implement + tune** (the descoped TODO items): make matched-control subtraction a
   first-class FP mode, and re-check `recommend_fp_settings` against the subtracted EEM — it
   should now pick the real FP cell. This is also the moment to land the **raw emit + DARK
   count logging** (currently emit is stored only as a ratio), so subtraction has raw counts.

**Note the density caveat:** at plateau the FP3 base saturated ~40% of cycles on M0 — consider a
lower starting gain or a different base band for dense cultures, and/or scan earlier in growth.

---

## 5. Rollback (if the promoted server misbehaves)

```bash
ssh ChiBio 'cd /root/chibio && ./cb-stop.sh stop 5000'
# Known-good pre-refactor monolith:
ssh ChiBio 'cd /root/chibio-original-backup-2026-07-14 && ./cb.sh'
```
The guard is a small, isolated change (one helper + one line in `measure_fp`), so a full
rollback should not be necessary — but the path is here if needed.

---

## Quick reference — the saved safety-net values

| Reactor | OD0.target (blank) | Restore command |
|---|---|---|
| M0 | 15438.4 | `curl -X POST http://192.168.7.2:5000/CalibrateOD/OD0/M0/15438.4/0` |
| M1 | 15297.0 | `curl -X POST http://192.168.7.2:5000/CalibrateOD/OD0/M1/15297.0/0` |

Shared OD calibration (both): LASERa 0.226, LASERb 1.833, LEDAa 7.0, LEDFa 0.673, dark 0,
min 0, max 100000. Also recorded in the `od-blanking` memory.
