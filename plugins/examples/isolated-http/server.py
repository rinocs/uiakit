"""Minimal isolated HTTP plugin. Kept outside the runtime package and imported never."""
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROTOCOL = 1


def plugin_token() -> str:
    """Resolve the token from the environment or a mounted file, per request."""
    value = os.environ.get('ISOLATED_PLUGIN_TOKEN', '')
    path = os.environ.get('ISOLATED_PLUGIN_TOKEN_FILE', '')
    if value and path:
        raise SystemExit('ambiguous ISOLATED_PLUGIN_TOKEN configuration')
    if path:
        try:
            with open(path, encoding='utf-8') as handle:
                value = handle.read(8193).rstrip('\n')
        except OSError:
            raise SystemExit('ISOLATED_PLUGIN_TOKEN_FILE unreadable') from None
    if not value or len(value) > 8192:
        raise SystemExit('ISOLATED_PLUGIN_TOKEN required')
    return value
MAX_BODY = 131072
TOOLS = [{
    'id': 'echo',
    'name': 'Echo',
    'description': 'Return the supplied text from the isolated process.',
    'version': '1.0.0',
    'connector': 'isolated_example',
    'timeout': 2,
    'input_schema': {
        'type': 'object', 'additionalProperties': False, 'required': ['text'],
        'properties': {'text': {'type': 'string', 'maxLength': 1000}},
    },
    'output_schema': {
        'type': 'object', 'additionalProperties': False, 'required': ['text'],
        'properties': {'text': {'type': 'string', 'maxLength': 1000}},
    },
}]


class Handler(BaseHTTPRequestHandler):
    server_version = ''
    sys_version = ''

    def log_message(self, *_args):
        return

    def _send(self, status, payload):
        self.send_response(status)
        self.send_header('X-UAI-Plugin-Protocol', str(PROTOCOL))
        if status == 204:
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        data = json.dumps(payload, separators=(',', ':')).encode()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        expected = 'Bearer ' + plugin_token()
        return hmac.compare_digest(self.headers.get('Authorization', ''), expected) and \
            self.headers.get('X-UAI-Plugin-Protocol') == str(PROTOCOL)

    def _body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY:
            return None
        try:
            value = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, UnicodeError):
            return None
        return value if isinstance(value, dict) else None

    def do_GET(self):
        if not self._authorized():
            self._send(401, {'error': 'unauthorized'})
            return
        manifest = json.loads(Path(os.environ.get('ISOLATED_PLUGIN_MANIFEST', '/app/manifest.json')).read_text())
        if self.path == '/v1/health':
            self._send(200, {'protocol': PROTOCOL, 'status': 'ok'})
        elif self.path == '/v1/manifest':
            self._send(200, {'protocol': PROTOCOL, 'manifest': manifest})
        elif self.path == '/v1/tools':
            self._send(200, {'protocol': PROTOCOL, 'tools': TOOLS})
        else:
            self._send(404, {'error': 'not_found'})

    def do_POST(self):
        if not self._authorized():
            self._send(401, {'error': 'unauthorized'})
            return
        body = self._body()
        if body is None:
            self._send(422, {'error': 'invalid_body'})
            return
        if self.path in ('/v1/activate', '/v1/deactivate'):
            self._send(204, {'protocol': PROTOCOL})
            return
        prefix, suffix = '/v1/tools/', '/execute'
        if self.path.startswith(prefix) and self.path.endswith(suffix):
            local = self.path[len(prefix):-len(suffix)]
            tool = next((item for item in TOOLS if item['id'] == local), None)
            if tool is None:
                self._send(404, {'error': 'unknown_tool'})
                return
            arguments = body.get('arguments')
            text = arguments.get('text') if isinstance(arguments, dict) else None
            if not isinstance(text, str) or len(text) > 1000:
                self._send(422, {'error': 'invalid_arguments'})
                return
            self._send(200, {'protocol': PROTOCOL, 'result': {'text': text}})
            return
        self._send(404, {'error': 'not_found'})


if __name__ == '__main__':
    plugin_token()
    port = int(os.environ.get('ISOLATED_PLUGIN_PORT', '8090'))
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
