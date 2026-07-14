import os
import ipaddress
from flask import request, jsonify, g

# The BeagleBone USB-gadget point-to-point links. The directly-attached operator is
# always on one of these (192.168.7.0/24 on Windows/Linux, 192.168.6.0/24 on macOS),
# so their traffic is trusted without a token.
# ponytail: hardcoded; add an env override only if a deployment's link subnet differs.
TRUSTED_NETS = [ipaddress.ip_network('192.168.7.0/24'),
                ipaddress.ip_network('192.168.6.0/24')]

COOKIE_NAME = 'chibio_token'
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days — authenticate once, stay in.


def init_auth(app, logger):
    token = os.environ.get('CHIBIO_TOKEN', '')

    def is_local_request():
        addr = request.remote_addr or ''
        if addr.startswith('::ffff:'):
            addr = addr.split('::ffff:')[-1]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        # Trust loopback and the point-to-point USB link only — NOT all private IPs,
        # so a host sharing a LAN with the device cannot bypass the token.
        return ip.is_loopback or any(ip in net for net in TRUSTED_NETS)

    @app.before_request
    def require_token():
        if is_local_request():
            return
        # Non-local: require the token on every request (view and control alike).
        # Accept it from a query param / header (the one-time bootstrap) or the
        # cookie the browser then sends automatically on every request.
        presented = (request.args.get('token')
                     or request.headers.get('X-Auth-Token')
                     or request.cookies.get(COOKIE_NAME))
        if not token or presented != token:
            logger.warning('Unauthorized request: %s %s', request.method, request.path)
            return jsonify({'error': 'Unauthorized'}), 401
        # Hand back a cookie so the rest of the session is seamless — but only when
        # the token arrived out-of-band, not when it was already the cookie.
        g.set_auth_cookie = request.cookies.get(COOKIE_NAME) != token

    @app.after_request
    def persist_token(response):
        if getattr(g, 'set_auth_cookie', False):
            response.set_cookie(COOKIE_NAME, token, max_age=COOKIE_MAX_AGE,
                                httponly=True, samesite='Lax')
        return response
