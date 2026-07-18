#!/bin/bash
# fp_saturation_probe.sh — validate the FP near-saturation guard against a real dense culture,
# and map the gain->CLEAR-base knee. Run ON THE DEVICE (loopback is token-free).
#
# Context: the weekend stationary-phase cultures sit near the AS7341 CLEAR ceiling. At plateau
# M0 FP3 read base 58435-63840 (67% >= 60000), autorange landed at gain 7 and NEVER hit the
# exact-65535 that autorange retries on — so the near-saturated ratio was logged unflagged.
# The guard (_fp_valid_flag, chibio_measurements.py) flags valid=0 when base >= 60000. This
# probe drives FP3 across starting gains and prints base + the guard's valid flag so you can
# SEE it fire on M0 (saturating) and stay quiet on M1 (base ~45k, negative control).
#
# It turns on the excitation LED + stirrer, so it is an ACTUATING run — only launch on "go".
# Safe by construction: aborts unless the selected reactor's DeviceID matches the expected one
# (never measures an absent reactor -> no server crash), leaves FP3 off + stir off at the end.
#
# Usage on device:  ./fp_saturation_probe.sh M0
#                   ./fp_saturation_probe.sh M1 LEDD nm550 nm583 2048860525117957796
set -u
URL=http://127.0.0.1:5000
M=${1:-M0}
LED=${2:-LEDD}          # excitation LED. LEDD(523) drives this dense culture's CLEAR hard.
E1=${3:-nm550}          # emit band 1 (context only; base=CLEAR is what the guard watches)
E2=${4:-nm583}          # emit band 2
BASE=CLEAR
# Expected DeviceID guard (weekend rig): M0=6349460516117957796  M1=2048860525117957796
case "$M" in
  M0) EXPECT=${5:-6349460516117957796} ;;
  M1) EXPECT=${5:-2048860525117957796} ;;
  *)  EXPECT=${5:-} ;;
esac
GAINS="10 8 7 6 5 4"    # starting gain index (0..10 = 0.5x..512x); autorange only steps DOWN
                        # on a dense culture, so this traces base vs gain across the knee.
REPS=3                  # measures per gain (guard incidence over repeats)

post(){ curl -sf -X POST "$URL$1" -o /dev/null; }
fp3(){ curl -sf "$URL/getSysdata/" | python3 -c 'import sys,json;d=json.load(sys.stdin)["FP3"];print(d.get("Base"),round(d.get("Emit1",0),4),round(d.get("Emit2",0),4),d.get("GainUsed"),d.get("valid"),d.get("ON"))'; }
devid(){ curl -sf "$URL/getSysdata/" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("DeviceID"))'; }

echo "# fp_saturation_probe: M=$M LED=$LED emit=$E1/$E2 expect_id=$EXPECT"

# --- Safety: scan, select, and confirm we are really on the intended physical reactor ---
post "/scanDevices/all"; sleep 3
post "/changeDevice/$M"; sleep 1
GOT=$(devid)
if [ -n "$EXPECT" ] && [ "$GOT" != "$EXPECT" ]; then
  echo "ABORT: selected DeviceID=$GOT != expected $EXPECT (reactor absent or reslotted). No measurement taken."
  exit 1
fi
echo "# confirmed on DeviceID=$GOT"

# --- Stir on for a representative (mixed) read ---
post "/SetOutputTarget/Stir/$M/0.5"; post "/SetOutputOn/Stir/1/$M"; sleep 5

# --- Ensure FP3 starts OFF (SetFPMeasurement is a TOGGLE) ---
ON=$(curl -sf "$URL/getSysdata/" | python3 -c 'import sys,json;print(json.load(sys.stdin)["FP3"]["ON"])')
[ "$ON" = "1" ] && post "/SetFPMeasurement/FP3/$LED/$BASE/$E1/$E2/x10"

printf "%-6s %-4s %-8s %-8s %-8s %-9s %-5s\n" gain_start rep base emit1 emit2 gain_used valid
for g in $GAINS; do
  post "/SetFPMeasurement/FP3/$LED/$BASE/$E1/$E2/x$g"   # OFF -> ON + config at start gain x$g
  for r in $(seq 1 $REPS); do
    post "/MeasureFP/$M"; sleep 5                        # MeasureFP is async; let autorange (<=4 retries @255 steps) settle
    read B M1v M2v GU V _ < <(fp3)
    printf "x%-5s %-4s %-8s %-8s %-8s %-9s %-5s\n" "$g" "$r" "$B" "$M1v" "$M2v" "$GU" "$V"
  done
  post "/SetFPMeasurement/FP3/$LED/$BASE/$E1/$E2/x$g"   # toggle FP3 back OFF for the next gain
done

# --- Teardown: FP3 already off; stir off ---
post "/SetOutputOn/Stir/0/$M"
echo "# done. valid=0 rows are the guard firing (base >= 60000). FP3 left OFF, stir OFF."
