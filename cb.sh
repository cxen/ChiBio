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

# Uncomment the following line to run ChiBio in the background
# screen -dmS ChiBio bash -c "gunicorn -b 0.0.0.0:5000 app:application"
# Then, comment out the next line
gunicorn -b 0.0.0.0:5000 app:application
