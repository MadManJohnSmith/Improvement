"""python3 -B -m unittest discover -s tests -p test_inference_channel.py -v"""
import http.server
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_launcher import launch
from inference_channel import Inference


class InferenceTest(unittest.TestCase):
    def test_isolated_channel(self):
        seen = []
        secret = 'fixture-host-only-secret'

        class Fixture(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, dict(self.headers), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body = b'{"choices":[{"message":{"content":"OK"}}]}'
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        with http.server.HTTPServer(('127.0.0.1', 0), Fixture) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = Path(tempfile.mkdtemp(prefix='inference-regression-', dir='/tmp'))
            product = root / 'product'
            product.mkdir()
            runs = root / 'runs'
            runs.mkdir()
            check = product / 'check.py'
            check.write_text('''import os, json, urllib.request, urllib.error, socket
url = os.environ['INFERENCE_BASE_URL'] + '/chat/completions'
body = json.dumps({'model':'fixture','messages':[{'role':'user','content':'OK'}],'max_tokens':4}).encode()
for path in ['/admin', '/chat/completions?url=http://evil', '/http://evil']:
    try: urllib.request.urlopen(urllib.request.Request(os.environ['INFERENCE_BASE_URL']+path,data=body))
    except urllib.error.HTTPError as e: assert e.code == 403
    else: raise AssertionError('path accepted')
try: urllib.request.urlopen(url)
except urllib.error.HTTPError as e: assert e.code == 501
try: socket.create_connection(('127.0.0.1', int(os.environ['FIXTURE_PORT'])),1)
except OSError: pass
else: raise AssertionError('host network exposed')
request=urllib.request.Request(url,data=body,headers={'Authorization':'Bearer attacker','X-Admin':'yes','Content-Type':'application/json'})
assert b'OK' in urllib.request.urlopen(request).read()
try: urllib.request.urlopen(request)
except urllib.error.HTTPError as e: assert e.code == 502
else: raise AssertionError('quota bypassed')
assert 'fixture-host-only-secret' not in str(dict(os.environ))
print('isolated inference PASS')
''')
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            channel = Inference(endpoint=endpoint, model='fixture', authorization='Bearer ' + secret)
            state, code = launch(reads={'product':product}, cwd=product, state_parent=runs,
                                 argv=['/usr/bin/env', f'FIXTURE_PORT={server.server_port}', '/usr/bin/python3', '-B', str(check)], inference=channel)
            server.shutdown()
            thread.join()
        self.assertEqual(code, 0, (state / 'stderr.log').read_text())
        self.assertEqual(len(seen), 1)
        path, headers, body = seen[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(headers['Authorization'], 'Bearer ' + secret)
        self.assertNotIn('X-Admin', headers)
        for log in state.glob('*.log'):
            self.assertNotIn(secret, log.read_text())
        print(f'Inference isolation evidence: {root}')

    def test_reject_and_response_limits(self):
        hits = []
        class Fixture(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(302 if len(hits) == 1 else 200)
                self.send_header('Location', '/admin')
                self.end_headers()
                if len(hits) == 2:
                    self.wfile.write(b'x' * 1048577)
                elif len(hits) == 3:
                    self.wfile.write(b'fixture-secret-value')
            def log_message(self, *args):
                pass
        with http.server.HTTPServer(('127.0.0.1', 0), Fixture) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            payload = json.dumps({'model':'fixture','messages':[{'role':'user','content':'OK'}],'max_tokens':4}).encode()
            for bad in [b'[]', b'{}', b'x'*65537, payload.replace(b'fixture',b'other')]:
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture').request(bad)
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture').request(payload)
            self.assertEqual(hits, ['/v1/chat/completions'])
            for _ in range(2):
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret-value').request(payload)
            native = payload.replace(b'"max_tokens": 4', b'"max_completion_tokens": 4, "store": false')
            self.assertEqual(Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret-value').request(native), b'')
            server.shutdown()
            thread.join()
        for endpoint in ['http://evil/v1/chat/completions', 'http://127.0.0.1:80/admin', 'http://user@127.0.0.1/v1/chat/completions', 'http://127.0.0.1/v1/chat/completions?x=1']:
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture')

    def test_tool_turn_allowlist(self):
        """Structural turn keys: a tools turn passes; unlisted keys and shapes fail closed."""
        hits = []

        class Fixture(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"OK"}}]}')

            def log_message(self, *args):
                pass

        with http.server.HTTPServer(('127.0.0.1', 0), Fixture) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            tool = {'type': 'function', 'function': {'name': 'fs_read', 'description': 'read a file',
                    'parameters': {'type': 'object', 'properties': {}}, 'strict': False}}
            base = {'model': 'fixture', 'stream': True, 'store': False,
                    'stream_options': {'include_usage': True}, 'max_completion_tokens': 16,
                    'tools': [tool],
                    'messages': [{'role': 'system', 'content': 'sys'},
                                 {'role': 'user', 'content': 'list files'}]}
            # The child turn carrying tools is accepted and reaches the upstream.
            body = Inference(endpoint=endpoint, model='fixture',
                             authorization='Bearer fixture-secret').request(json.dumps(base).encode())
            self.assertEqual(body, b'{"choices":[{"message":{"content":"OK"}}]}')
            # Second leg of a full turn: assistant tool_calls plus tool result accepted.
            followup = dict(base, messages=base['messages'] + [
                {'role': 'assistant', 'content': None,
                 'tool_calls': [{'id': 'call_1', 'type': 'function',
                                 'function': {'name': 'fs_read', 'arguments': '{"path":"a"}'}}]},
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'file body'},
            ])
            self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                       authorization='Bearer fixture-secret').request(json.dumps(followup).encode()), body)
            self.assertEqual(hits, ['/v1/chat/completions', '/v1/chat/completions'])
            # Fail-closed: unlisted payload keys never reach the upstream.
            for extra in ({'logprobs': True}, {'user': 'x'}, {'parallel_tool_calls': False},
                          {'response_format': {'type': 'json_object'}}):
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret').request(
                        json.dumps(dict(base, **extra)).encode())
            # Malformed structural shapes stay denied.
            bad_tools = [dict(base, tools=['x']), dict(base, tools=[dict(tool, extra=1)]),
                         dict(base, tools=[{'type': 'custom', 'function': {'name': 'n'}}]),
                         dict(base, tools=[{'type': 'function', 'function': {'parameters': {}}}]),
                         dict(base, tool_choice='any'), dict(base, tool_choice={'type': 'function'})]
            bad_messages = [dict(base, messages=base['messages'] + [
                                {'role': 'assistant', 'content': None,
                                 'tool_calls': [{'id': 'c', 'type': 'function',
                                                 'function': {'name': 'n', 'arguments': '{}', 'extra': 1}}]}]),
                            dict(base, messages=base['messages'] + [
                                {'role': 'assistant', 'content': None,
                                 'tool_calls': [{'id': 'c', 'type': 'function',
                                                 'function': {'name': 'n', 'arguments': '{}'}}],
                                 'reasoning_details': []}]),
                            dict(base, messages=base['messages'] + [{'role': 'tool', 'content': 'x'}]),
                            dict(base, messages=base['messages'] + [{'role': 'developer', 'content': 'x'}])]
            for bad in bad_tools + bad_messages:
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret').request(
                        json.dumps(bad).encode())
            self.assertEqual(hits, ['/v1/chat/completions', '/v1/chat/completions'])
            # Empty tools list is exactly what the runtime sends for tool history only.
            history = dict(base, tool_choice='none', tools=[{'type': 'function', 'function': {'name': 'n'}}])
            self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                       authorization='Bearer fixture-secret').request(json.dumps(history).encode()), body)
            server.shutdown()
            thread.join()

    def test_upstream_deadline(self):
        class Slow(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.send_header('Content-Length', '100')
                self.end_headers()
                try:
                    for _ in range(25):
                        self.wfile.write(b'x')
                        self.wfile.flush()
                        time.sleep(1)
                except OSError:
                    pass
            def log_message(self, *args):
                pass
        with http.server.HTTPServer(('127.0.0.1', 0), Slow) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            channel = Inference(endpoint=f'http://127.0.0.1:{server.server_port}/v1/chat/completions', model='fixture', authorization='Bearer fixture-secret')
            start = time.monotonic()
            with self.assertRaises((ValueError, OSError, http.client.HTTPException)):
                channel.request(json.dumps({'model':'fixture','messages':[{'role':'user','content':'OK'}],'max_tokens':4}).encode())
            self.assertLess(time.monotonic() - start, 23)
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    unittest.main()
