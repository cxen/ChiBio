import os
import ipaddress
from flask import request, jsonify


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
        return ip.is_private or ip.is_loopback

    @app.before_request
    def require_token():
        if is_local_request():
            return
        if request.method != 'POST':
            return
        if not token:
            logger.warning('Open access (no token) for non-local request: %s %s', request.method, request.path)
            return
        req_token = request.headers.get('X-Auth-Token') or request.args.get('token')
        if req_token != token:
            logger.warning('Unauthorized request: %s %s', request.method, request.path)
            return jsonify({'error': 'Unauthorized'}), 401
