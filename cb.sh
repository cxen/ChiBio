# Load CHIBIO_TOKEN from a local, gitignored file if present, so the shared
# secret stays out of shell history and source control. No file => unset (auth
# then denies non-local requests; see chibio_auth.py). Point-to-point USB access
# never needs the token.
_tok="$(dirname "$0")/.chibio_token"
[ -f "$_tok" ] && export CHIBIO_TOKEN="$(cat "$_tok")"

# Bind 0.0.0.0 so the UI is served on BOTH the USB point-to-point link and the
# LAN. LAN (non-local) requests require the token; USB requests are trusted.

# Print the URLs the GUI is actually reachable on, so nobody has to work out the
# device's address or hand-append the token (README documented this by hand).
# chibio_auth.py trusts loopback + the USB-gadget subnets; every other address
# needs ?token=, so only those lines carry it.
echo "✨ ChiBio bioreactor OS (gunicorn on 0.0.0.0:5000)"

# Say it before the URLs, not after: the whole point of the simulator is that the UI
# looks exactly like a real run, so the one place an operator can tell them apart is
# here and the SIM- device IDs / terminal line in the GUI itself.
if [ -n "$CHIBIO_SIM" ]; then
  echo "   🧪 SIMULATION MODE — fake I2C bus, no hardware. Readings are modelled, not measured."
  echo "      Reactors: ${CHIBIO_SIM_REACTORS:-M0,M1,M2,M3,M4} | LED version: ${CHIBIO_SIM_LED_VERSION:-2} | history: ${CHIBIO_SIM_HOURS:-12}h"
fi
for _ip in $(hostname -I 2>/dev/null); do
  case "$_ip" in
    192.168.7.*|192.168.6.*)
      echo "   Open the ChiBio GUI: http://$_ip:5000/"
      echo "   USB point-to-point link — trusted, no token needed."
      ;;
    127.*) ;;
    *)
      if [ -n "$CHIBIO_TOKEN" ]; then
        echo "   Open the ChiBio GUI: http://$_ip:5000/?token=$CHIBIO_TOKEN"
        [ -n "$SSH_CONNECTION" ] && echo "   SSH session detected — click the link above, no port forwarding needed."
      else
        echo "   LAN address http://$_ip:5000/ — no CHIBIO_TOKEN set, so remote access is denied."
      fi
      ;;
  esac
done
echo

# --timeout 300: gunicorn's default is 30 s, and that is FATAL here. The worker
# runs the experiment threads in-process; five reactors each doing 3x OD plus
# 3 FP slots x 3 replicates per cycle, all serialized through the single global
# I2C lock on a single-core BeagleBone, can starve the worker's heartbeat past
# 30 s. The master then kills it -- and because ALL experiment state lives in
# RAM (sysData), a worker restart silently ends every running experiment: blanks
# reset to the 65000 default, FP config clears, cycles goes back to 0, and only
# the CSV rows already flushed to disk survive. Observed 2026-08-11 20:12:57,
# "[CRITICAL] WORKER TIMEOUT (pid:1258)", which killed a live 5-reactor run three
# minutes in. Raise the ceiling well clear of the worst cycle.
# --graceful-timeout 60: give a worker that IS shutting down time to finish a
# cycle's CSV write rather than losing the row.
# Uncomment the following line to run ChiBio in the background
# screen -dmS ChiBio bash -c "gunicorn --timeout 300 --graceful-timeout 60 -b 0.0.0.0:5000 app:application"
# Then, comment out the next line
gunicorn --timeout 300 --graceful-timeout 60 -b 0.0.0.0:5000 app:application
