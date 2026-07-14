import os
import ipaddress
from flask import request, jsonify


# The BeagleBone USB-gadget point-to-point links. The directly-attached host is
# always on one of these (192.168.7.0/24 on Windows/Linux, 192.168.6.0/24 on macOS),
# so traffic from them is the physically-connected operator and is trusted.
# ponytail: hardcoded; add an env override only if a deployment's link subnet differs.
TRUSTED_NETS = [ipaddress.ip_network('192.168.7.0/24'),
                ipaddress.ip_network('192.168.6.0/24')]


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
        if request.method != 'POST':
            return
        # Fail closed: no token configured => no non-local POST can authenticate.
        req_token = request.headers.get('X-Auth-Token') or request.args.get('token')
        if not token or req_token != token:
            logger.warning('Unauthorized request: %s %s', request.method, request.path)
            return jsonify({'error': 'Unauthorized'}), 401
