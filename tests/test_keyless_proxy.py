"""El proxy keyless elimina la credencial y reenvía al upstream íntegro.

El tier gratuito de opencode solo acepta peticiones sin cabecera de
autenticación y pi-ai de DSH siempre exige una credencial: el modo keyless
del workflow interpone este proxy (eval/keyless_proxy.py) en el runner.
Esta prueba lo ejercita offline contra un upstream stub: sin cabecera de
autenticación aguas arriba, ruta mapeada sin duplicar ``/v1``, cuerpo y
respuesta retransmitidos.
"""

import http.client
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "eval" / "keyless_proxy.py"


class _StubUpstream(BaseHTTPRequestHandler):
    seen = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).seen = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": json.loads(body) if body else None,
        }
        payload = b"data: {\"ok\": true}\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


class KeylessProxyTest(unittest.TestCase):
    def test_the_proxy_strips_the_credential_and_forwards_the_stream(self):
        """Sin Authorization aguas arriba, ruta sin /v1 duplicado, SSE íntegro.

        pi-ai envía `Bearer <credencial>`; el proxy debe eliminar la
        cabecera (el cupo anónimo del proveedor la rechaza con
        authentication_error), mapear /v1/chat/completions contra la base
        del upstream y devolver el cuerpo tal cual.
        """
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StubUpstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        self.addCleanup(upstream.shutdown)
        upstream_port = upstream.server_address[1]

        environment = dict(
            os.environ,
            # La forma real del upstream de opencode: la base lleva su /v1.
            UPSTREAM_BASE=f"http://127.0.0.1:{upstream_port}/inference/openai/v1",
            PROXY_PORT="18091")
        proxy = subprocess.Popen(
            [sys.executable, "-B", str(PROXY)], env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Los cleanups corren en LIFO: terminar antes de esperar.
        self.addCleanup(proxy.wait)
        self.addCleanup(proxy.terminate)
        for _ in range(40):
            try:
                probe = http.client.HTTPConnection("127.0.0.1", 18091,
                                                   timeout=2)
                probe.request("GET", "/health")
                probe.close()
                break
            except OSError:
                if proxy.poll() is not None:
                    self.fail("el proxy murió al arrancar")
                time.sleep(0.25)

        client = http.client.HTTPConnection("127.0.0.1", 18091, timeout=10)
        payload = json.dumps({"model": "deepseek-v4.1-flash-free",
                              "messages": [{"role": "user",
                                            "content": "di ok"}]})
        client.request("POST", "/v1/chat/completions", body=payload,
                       headers={"Content-Type": "application/json",
                                "Authorization": "Bearer anonymous"})
        response = client.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn(b'"ok": true', response.read())
        client.close()

        self.assertEqual(_StubUpstream.seen["path"],
                         "/inference/openai/v1/chat/completions",
                         "la ruta /v1 del cliente no debe duplicarse")
        self.assertIsNone(_StubUpstream.seen["authorization"],
                          "la credencial debe eliminarse aguas arriba")
        self.assertEqual(_StubUpstream.seen["body"]["model"],
                         "deepseek-v4.1-flash-free")


if __name__ == "__main__":
    unittest.main()
