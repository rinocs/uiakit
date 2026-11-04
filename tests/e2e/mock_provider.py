"""Offline OpenAI-compatible fixture; never enabled by default deployment."""
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/v1/models':
            data = json.dumps({'data': [{'id': 'test'}, {'id': 'test2'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            return
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/embed':
            texts = body.get('input')
            assert isinstance(texts, list) and texts
            embeddings = []
            for text in texts:
                seed = hashlib.sha256(text.encode()).digest()
                embeddings.append([(seed[i] / 255.0) for i in range(8)])
            data = json.dumps({'model': body.get('model', 'test-embed'), 'embeddings': embeddings}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            return
        assert self.path == '/v1/chat/completions'
        assert body['stream'] is True
        last = body['messages'][-1]
        content = last.get('content') or ''
        if content == '__e2e_slow__':
            time.sleep(10)
        if last.get('role') == 'tool':
            text = 'Tool result: ' + content
            chunks = [
                {'choices': [{'delta': {'content': text}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                {'choices': [], 'usage': {'prompt_tokens': 5, 'completion_tokens': 4, 'total_tokens': 9}},
            ]
        elif content in ('__e2e_tool_read__', '__e2e_tool_unauthorized__', '__e2e_tool_storm__'):
            if content == '__e2e_tool_unauthorized__':
                calls = [{'index': 0, 'id': 'call-unauthorized', 'type': 'function',
                          'function': {'name': 'mocktool.write',
                                       'arguments': '{"value":"forbidden"}'}}]
            elif content == '__e2e_tool_storm__':
                calls = [
                    {'index': 0, 'id': 'call-storm-1', 'type': 'function',
                     'function': {'name': 'mocktool.read', 'arguments': '{"q":"one"}'}},
                    {'index': 1, 'id': 'call-storm-2', 'type': 'function',
                     'function': {'name': 'mocktool.read', 'arguments': '{"q":"two"}'}},
                ]
            else:
                calls = [{'index': 0, 'id': 'call-read', 'type': 'function',
                          'function': {'name': 'mocktool.read',
                                       'arguments': '{"q":"hello"}'}}]
            chunks = [
                {'choices': [{'delta': {'tool_calls': calls}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'tool_calls'}]},
                {'choices': [], 'usage': {'prompt_tokens': 5, 'completion_tokens': 4, 'total_tokens': 9}},
            ]
        else:
            text = ' \n ' if content == '__e2e_whitespace__' else 'Risposta mock: ' + content
            chunks = [
                {'choices': [{'delta': {'content': text}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
                {'choices': [], 'usage': {'prompt_tokens': 5, 'completion_tokens': 4, 'total_tokens': 9}},
            ]
        data = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'
        data = data.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 9000), Handler).serve_forever()
