# Load CHIBIO_TOKEN from a local, gitignored file if present, so the shared
# secret stays out of shell history and source control. No file => unset (auth
# then denies non-local requests; see chibio_auth.py). Point-to-point USB access
# never needs the token.
_tok="$(dirname "$0")/.chibio_token"
[ -f "$_tok" ] && export CHIBIO_TOKEN="$(cat "$_tok")"

# Bind 0.0.0.0 so the UI is served on BOTH the USB point-to-point link and the
# LAN. LAN (non-local) requests require the token; USB requests are trusted.

# Uncomment the following line to run ChiBio in the background
# screen -dmS ChiBio bash -c "gunicorn -b 0.0.0.0:5000 app:application"
# Then, comment out the next line
gunicorn -b 0.0.0.0:5000 app:application
