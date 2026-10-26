"""Offline HTTP tool fixture: read endpoint, mutating effect endpoint and stats."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

LOCK = threading.Lock()
STATE = {'reads': 0, 'writes': 0, 'effects': [], 'last_idempotency_key': None}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args):
        return

    def _send(self, status, payload):
        data = json.dumps(payload, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/health':
            self._send(200, {'status': 'ok'})
        elif parsed.path == '/stats':
            with LOCK:
                self._send(200, dict(STATE))
        elif parsed.path == '/read':
            q = parse_qs(parsed.query).get('q', [''])[0]
            with LOCK:
                STATE['reads'] += 1
            self._send(200, {'result': q})
        else:
            self._send(404, {'error': 'not_found'})

    def do_POST(self):
        if self.path != '/write':
            self._send(404, {'error': 'not_found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, UnicodeError):
            self._send(422, {'error': 'invalid_body'})
            return
        value = body.get('value') if isinstance(body, dict) else None
        if not isinstance(value, str) or len(value) > 1000:
            self._send(422, {'error': 'invalid_arguments'})
            return
        key = self.headers.get('Idempotency-Key')
        with LOCK:
            if key and key == STATE['last_idempotency_key']:
                result = {'written': value, 'duplicate': True}
            else:
                STATE['writes'] += 1
                STATE['effects'].append(value)
                STATE['last_idempotency_key'] = key
                result = {'written': value, 'duplicate': False}
        self._send(200, result)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 9100), Handler).serve_forever()
