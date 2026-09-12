"""One-request loopback inference capability over anonymous stdin/stdout pipes."""
import http.client
import http.server
import json
import os
import struct
import socket
import subprocess
import sys
import threading
from urllib.parse import urlsplit

LIMIT = 65536
RESPONSE_LIMIT = 1048576


def receive(stream, limit):
    size = stream.read(4)
    if len(size) != 4:
        raise ValueError('Closed channel')
    length = struct.unpack('!I', size)[0]
    if length > limit:
        raise ValueError('Frame limit')
    data = stream.read(length)
    if len(data) != length:
        raise ValueError('Incomplete frame')
    return data


def send(stream, data):
    stream.write(struct.pack('!I', len(data)) + data)
    stream.flush()


class Inference:
    def __init__(self, *, endpoint, model, authorization):
        url = urlsplit(endpoint)
        # ponytail: existing local OpenAI gateway only; add another protocol after fixtures.
        if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1')
                or url.username or url.password or url.path != '/v1/chat/completions'
                or url.query or url.fragment or not url.port):
            raise ValueError('Only explicit loopback chat completion endpoint allowed')
        if not model or not authorization or any(c in authorization for c in '\r\n'):
            raise ValueError('Model and safe host authorization required')
        self.port, self.model, self.authorization = url.port, model, authorization
        self.used = False

    def request(self, data):
        if self.used or len(data) > LIMIT:
            raise ValueError('Request budget exhausted')
        self.used = True
        payload = json.loads(data)
        allowed = {'model', 'messages', 'max_tokens', 'max_completion_tokens', 'store', 'stream', 'stream_options', 'temperature', 'top_p'}
        tokens = payload.get('max_tokens', payload.get('max_completion_tokens')) if isinstance(payload, dict) else None
        if (not isinstance(payload, dict) or set(payload) - allowed
                or payload.get('model') != self.model
                or not isinstance(payload.get('messages'), list)
                or not 1 <= len(payload['messages']) <= 8
                or ('max_tokens' in payload and 'max_completion_tokens' in payload)
                or payload.get('store', False) is not False
                or type(payload.get('stream', False)) is not bool
                or payload.get('stream_options', {'include_usage': True}) != {'include_usage': True}
                or type(tokens) is not int or not 1 <= tokens <= 32):
            raise ValueError('Inference payload denied')
        for message in payload['messages']:
            if (not isinstance(message, dict) or set(message) != {'role', 'content'}
                    or message['role'] not in ('system', 'user', 'assistant')
                    or not isinstance(message['content'], str)):
                raise ValueError('Text messages only')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=20)
        connection.connect()
        transport = connection.sock
        expired = threading.Event()
        def expire():
            expired.set()
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = threading.Timer(20, expire)
        deadline.start()
        try:
            connection.request('POST', '/v1/chat/completions', body=data,
                               headers={'Authorization':self.authorization, 'Content-Type':'application/json', 'Accept-Encoding':'identity'})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(f'Upstream status {response.status}')
            body = response.read(RESPONSE_LIMIT + 1)
            if (expired.is_set() or response.length is not None and response.length != len(body)
                    or len(body) > RESPONSE_LIMIT or self.authorization.encode() in body
                    or self.authorization.removeprefix('Bearer ').encode() in body):
                raise ValueError('Response denied')
            return body
        finally:
            deadline.cancel()
            deadline.join()
            connection.close()

    def serve(self, incoming, outgoing):
        try:
            while True:
                data = receive(incoming, LIMIT)
                try:
                    body = b'\x01' + self.request(data)
                except (ValueError, OSError, http.client.HTTPException):
                    body = b'\x00'
                send(outgoing, body)
        except (ValueError, OSError):
            pass


def isolated(argv):
    incoming, outgoing = sys.stdin.buffer, sys.stdout.buffer
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/v1/chat/completions':
                self.send_error(403)
                return
            sizes = self.headers.get_all('Content-Length', [])
            if (len(sizes) != 1 or not sizes[0].isdigit() or not 0 < int(sizes[0]) <= LIMIT
                    or self.headers.get('Transfer-Encoding')):
                self.send_error(400)
                return
            self.connection.settimeout(25)
            try:
                data = self.rfile.read(int(sizes[0]))
                if len(data) != int(sizes[0]):
                    raise ValueError('Incomplete body')
                send(outgoing, data)
                body = receive(incoming, RESPONSE_LIMIT + 1)
                if body[:1] != b'\x01':
                    raise ValueError('Inference denied')
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream' if json.loads(data).get('stream') else 'application/json')
                self.send_header('Content-Length', str(len(body)-1))
                self.end_headers()
                self.wfile.write(body[1:])
            except (OSError, ValueError):
                self.send_error(502, 'Inference unavailable')
        def log_message(self, *args):
            pass
    with http.server.HTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = dict(os.environ, INFERENCE_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1')
        with open('/state/stdout.log', 'wb') as out:
            result = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=sys.stderr, close_fds=True)
        server.shutdown()
        thread.join()
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(isolated(sys.argv[1:]))
