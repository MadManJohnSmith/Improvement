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
from inference_channel import (DEFAULT_MESSAGES, DEFAULT_PAYLOAD_LIMIT, DEFAULT_REQUESTS,
                               MAX_MESSAGES, MAX_PAYLOAD_LIMIT, MAX_REQUESTS, MAX_TOKENS,
                               BudgetExhausted, Inference)


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
except urllib.error.HTTPError as e: assert e.code == 503 and b'budget' in e.read()
else: raise AssertionError('budget bypassed')
try: urllib.request.urlopen(request)
except urllib.error.HTTPError as e: assert e.code == 502
else: raise AssertionError('channel not cut after budget')
assert 'fixture-host-only-secret' not in str(dict(os.environ))
print('isolated inference PASS')
''')
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            channel = Inference(endpoint=endpoint, model='fixture', authorization='Bearer ' + secret, requests=1)
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
        self.assertIn('FAIL CLOSED: inference request budget exhausted', (state / 'stderr.log').read_text())
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
            for bad in [b'[]', b'{}', b'x' * (DEFAULT_PAYLOAD_LIMIT + 1), payload.replace(b'fixture', b'other')]:
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

    def test_multi_request_budget_and_quotas(self):
        """Session channel: in-budget multi-request passes; exhaustion cuts fail-closed;
        per-launch token/message ceilings apply; quota arguments are validated."""
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
            self.assertEqual((DEFAULT_REQUESTS, MAX_REQUESTS, MAX_TOKENS,
                              DEFAULT_MESSAGES, MAX_MESSAGES), (12, 256, 32768, 64, 256))
            ok = b'{"choices":[{"message":{"content":"OK"}}]}'
            body = json.dumps({'model': 'fixture', 'messages': [{'role': 'user', 'content': 'OK'}],
                               'max_tokens': 32768}).encode()
            # Multi-request session within a per-launch budget of 3.
            channel = Inference(endpoint=endpoint, model='fixture',
                                authorization='Bearer fixture-secret', requests=3)
            for _ in range(3):
                self.assertEqual(channel.request(body), ok)
            self.assertEqual(hits, ['/v1/chat/completions'] * 3)
            with self.assertRaises(BudgetExhausted):
                channel.request(body)
            self.assertEqual(hits, ['/v1/chat/completions'] * 3)
            # Quota arguments are validated fail-closed (bool excluded).
            for kwargs in ({'requests': 0}, {'requests': MAX_REQUESTS + 1}, {'requests': True},
                           {'requests': '3'}, {'max_tokens': 0}, {'max_tokens': MAX_TOKENS + 1},
                           {'messages': 0}, {'messages': MAX_MESSAGES + 1}):
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer s', **kwargs)
            # New token ceiling: the child-loop default 32768 passes, 32769 is denied.
            self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                       authorization='Bearer fixture-secret').request(body), ok)
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret').request(
                    body.replace(b'32768', b'32769'))
            # A lower per-launch token ceiling applies to that launch only.
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                          max_tokens=16).request(body)
            # Message quota: the default launch keeps the conservative 64-message
            # request ceiling; a launch may raise it up to the hard cap.
            full = json.dumps({'model': 'fixture',
                               'messages': [{'role': 'user', 'content': 'OK'}] * DEFAULT_MESSAGES,
                               'max_tokens': 1}).encode()
            self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                       authorization='Bearer fixture-secret').request(full), ok)
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret').request(
                    json.dumps({'model': 'fixture',
                                'messages': [{'role': 'user', 'content': 'OK'}] * (DEFAULT_MESSAGES + 1),
                                'max_tokens': 1}).encode())
            raised = json.dumps({'model': 'fixture',
                                 'messages': [{'role': 'user', 'content': 'OK'}] * MAX_MESSAGES,
                                 'max_tokens': 1}).encode()
            self.assertEqual(Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                                       messages=MAX_MESSAGES).request(raised), ok)
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                          messages=MAX_MESSAGES).request(
                    json.dumps({'model': 'fixture',
                                'messages': [{'role': 'user', 'content': 'OK'}] * (MAX_MESSAGES + 1),
                                'max_tokens': 1}).encode())
            # A lower per-launch message ceiling still applies to that launch only.
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                          messages=2).request(json.dumps({'model': 'fixture',
                                                          'messages': [{'role': 'user', 'content': 'a'},
                                                                       {'role': 'user', 'content': 'b'},
                                                                       {'role': 'user', 'content': 'c'}],
                                                          'max_tokens': 1}).encode())
            self.assertEqual(hits, ['/v1/chat/completions'] * 6)
            server.shutdown()
            thread.join()

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

    def test_payload_limit_and_reasoning_parts(self):
        """Per-launch payload ceiling (1 MiB default, 8 MiB hard cap) enforced at the
        broker, and the assistant reasoning/textual shapes the installed runtime emits."""
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
            self.assertEqual((DEFAULT_PAYLOAD_LIMIT, MAX_PAYLOAD_LIMIT), (1048576, 8388608))
            ok = b'{"choices":[{"message":{"content":"OK"}}]}'
            # A conversation above the old 64 KiB frame now passes at the default ceiling.
            big = json.dumps({'model': 'fixture', 'max_tokens': 4,
                              'messages': [{'role': 'user', 'content': 'x' * 70000}]}).encode()
            self.assertGreater(len(big), 65536)
            self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                       authorization='Bearer fixture-secret').request(big), ok)
            # A lower per-launch ceiling denies the same payload without reaching upstream.
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                          payload_limit=1024).request(big)
            # The hard cap holds even when the launch asks for the maximum.
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret',
                          payload_limit=MAX_PAYLOAD_LIMIT).request(b'x' * (MAX_PAYLOAD_LIMIT + 1))
            # Quota arguments are validated like every other per-launch quota.
            for kwargs in ({'payload_limit': 0}, {'payload_limit': MAX_PAYLOAD_LIMIT + 1},
                           {'payload_limit': True}, {'payload_limit': '1048576'}):
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture', authorization='Bearer s', **kwargs)
            # Assistant reasoning fields and textual parts are exactly what the runtime
            # openai-completions conversion emits on the wire.
            base = {'model': 'fixture', 'max_tokens': 4,
                    'messages': [{'role': 'user', 'content': 'turn'}]}
            reasoning_turns = [
                {'role': 'assistant', 'content': 'answer', 'reasoning': 'thinking'},
                {'role': 'assistant', 'content': 'answer', 'reasoning_content': 'thinking'},
                {'role': 'assistant', 'content': 'answer', 'reasoning_text': 'thinking'},
                {'role': 'assistant', 'content': 'answer', 'reasoning': 'thinking',
                 'reasoning_content': ''},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 'part one'},
                                                  {'type': 'text', 'text': 'part two'}]},
                {'role': 'assistant', 'content': None,
                 'tool_calls': [{'id': 'call_1', 'type': 'function',
                                 'function': {'name': 'fs_read', 'arguments': '{}'}}],
                 'reasoning_content': 'thinking before the call'},
            ]
            for message in reasoning_turns:
                self.assertEqual(Inference(endpoint=endpoint, model='fixture',
                                           authorization='Bearer fixture-secret').request(
                    json.dumps(dict(base, messages=base['messages'] + [message])).encode()), ok)
            self.assertEqual(hits, ['/v1/chat/completions'] * (1 + len(reasoning_turns)))
            # Malformed reasoning and textual-part shapes stay denied before upstream.
            malformed = [
                {'role': 'assistant', 'content': 'answer', 'reasoning': 7},
                {'role': 'assistant', 'content': 'answer', 'reasoning_content': {'text': 'x'}},
                {'role': 'assistant', 'content': 'answer', 'reasoning': None},
                {'role': 'assistant', 'content': None, 'reasoning': 'thinking'},
                {'role': 'assistant', 'content': []},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 'a', 'extra': 1}]},
                {'role': 'assistant', 'content': [{'type': 'text'}]},
                {'role': 'assistant', 'content': [{'type': 'text', 'text': 3}]},
                {'role': 'assistant', 'content': [{'type': 'image_url', 'image_url': {'url': 'x'}}]},
                {'role': 'assistant', 'content': 'answer', 'thinking': 'unlisted key'},
            ]
            for message in malformed:
                with self.assertRaises(ValueError):
                    Inference(endpoint=endpoint, model='fixture',
                              authorization='Bearer fixture-secret').request(
                        json.dumps(dict(base, messages=base['messages'] + [message])).encode())
            # Minimal scope: textual part arrays stay denied outside assistant messages.
            with self.assertRaises(ValueError):
                Inference(endpoint=endpoint, model='fixture', authorization='Bearer fixture-secret').request(
                    json.dumps(dict(base, messages=[{'role': 'user',
                                                     'content': [{'type': 'text', 'text': 'x'}]}])).encode())
            self.assertEqual(hits, ['/v1/chat/completions'] * (1 + len(reasoning_turns)))
            server.shutdown()
            thread.join()

    def test_launch_payload_limit_end_to_end(self):
        """The per-launch payload limit reaches the sandboxed receiver: above the old
        64 KiB frame passes at the default ceiling; a small launch ceiling 400s early."""
        seen = []

        class Fixture(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(len(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"OK"}}]}')

            def log_message(self, *args):
                pass

        with http.server.HTTPServer(('127.0.0.1', 0), Fixture) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = Path(tempfile.mkdtemp(prefix='inference-payload-regression-', dir='/tmp'))
            product = root / 'product'
            product.mkdir()
            runs = root / 'runs'
            runs.mkdir()
            check = product / 'check.py'
            check.write_text('''import os, json, urllib.request
url = os.environ['INFERENCE_BASE_URL'] + '/chat/completions'
body = json.dumps({'model': 'fixture', 'max_tokens': 4,
                   'messages': [{'role': 'user', 'content': 'x' * 70000}]}).encode()
assert len(body) > 65536
print(urllib.request.urlopen(urllib.request.Request(url, data=body)).read().decode())
''')
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            state, code = launch(reads={'product': product}, cwd=product, state_parent=runs,
                                 argv=['/usr/bin/env', '/usr/bin/python3', '-B', str(check)],
                                 inference=Inference(endpoint=endpoint, model='fixture',
                                                     authorization='Bearer fixture-secret'))
            self.assertEqual(code, 0, (state / 'stderr.log').read_text())
            self.assertEqual((state / 'stdout.log').read_text().strip(),
                             '{"choices":[{"message":{"content":"OK"}}]}')
            # A launch ceiling below the payload size is enforced at the receiver itself:
            # HTTP 400 before any pipe or upstream traffic.
            small, code_small = launch(reads={'product': product}, cwd=product, state_parent=runs,
                                       argv=['/usr/bin/env', '/usr/bin/python3', '-B', str(check)],
                                       inference=Inference(endpoint=endpoint, model='fixture',
                                                           authorization='Bearer fixture-secret',
                                                           payload_limit=1024))
            self.assertEqual(code_small, 1)
            self.assertIn('HTTP Error 400', (small / 'stderr.log').read_text())
            self.assertEqual(len(seen), 1)
            self.assertGreater(seen[0], 65536)
            server.shutdown()
            thread.join()

    def test_launch_message_ceiling_end_to_end(self):
        """A per-launch raised message ceiling reaches a real launch: a 130-message
        request is denied at the default 64 and passes when the launch raises it."""
        seen = []

        class Fixture(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append(len(json.loads(self.rfile.read(int(self.headers['Content-Length'])))['messages']))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"OK"}}]}')

            def log_message(self, *args):
                pass

        with http.server.HTTPServer(('127.0.0.1', 0), Fixture) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = Path(tempfile.mkdtemp(prefix='inference-messages-regression-', dir='/tmp'))
            product = root / 'product'
            product.mkdir()
            runs = root / 'runs'
            runs.mkdir()
            check = product / 'check.py'
            check.write_text('''import os, json, urllib.request
url = os.environ['INFERENCE_BASE_URL'] + '/chat/completions'
body = json.dumps({'model': 'fixture', 'max_tokens': 4,
                   'messages': [{'role': 'user', 'content': 'OK'}] * 130}).encode()
print(urllib.request.urlopen(urllib.request.Request(url, data=body)).read().decode())
''')
            endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
            # Default launch keeps the 64-message ceiling: the broker denies fail-closed.
            state, code = launch(reads={'product': product}, cwd=product, state_parent=runs,
                                 argv=['/usr/bin/env', '/usr/bin/python3', '-B', str(check)],
                                 inference=Inference(endpoint=endpoint, model='fixture',
                                                     authorization='Bearer fixture-secret'))
            self.assertEqual(code, 1)
            self.assertIn('HTTP Error 502', (state / 'stderr.log').read_text())
            # The raised launch accepts the same conversation.
            state2, code2 = launch(reads={'product': product}, cwd=product, state_parent=runs,
                                   argv=['/usr/bin/env', '/usr/bin/python3', '-B', str(check)],
                                   inference=Inference(endpoint=endpoint, model='fixture',
                                                       authorization='Bearer fixture-secret',
                                                       messages=MAX_MESSAGES))
            self.assertEqual(code2, 0, (state2 / 'stderr.log').read_text())
            self.assertEqual((state2 / 'stdout.log').read_text().strip(),
                             '{"choices":[{"message":{"content":"OK"}}]}')
            self.assertEqual(seen, [130])
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
