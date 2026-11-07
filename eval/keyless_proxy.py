"""Proxy keyless del runner: elimina la credencial y reenvía al upstream.

El tier gratuito de opencode solo acepta peticiones SIN cabecera de
autenticación (cualquier Bearer no vacío responde `authentication_error`,
verificado contra su endpoint público), pero pi-ai de DSH siempre exige
una credencial (`No API key for provider`). El patrón es el de OmniRoute:
el cliente habla con un proxy local que quita la cabecera Authorization y
reenvía al upstream tal cual. Solo stdlib; la respuesta (incluido el
streaming SSE) se retransmite por trozos.

Configuración por entorno: ``UPSTREAM_BASE`` (URL base pública del
proveedor) y ``PROXY_PORT`` (defecto 8091). El perfil de DSH declara el
proxy como baseURL sin ruta (``http://127.0.0.1:$PROXY_PORT``) y DSH añade
``/v1/...``; el upstream ya lleva su ``/v1``, así que el prefijo se
elimina para no duplicarlo.
"""

import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# Cabeceras que el proxy no reenvía: la credencial se elimina (el sentido
# del proxy), Host la fija http.client contra el upstream y el cuerpo y la
# codificación los negocia este lado.
DROPPED_HEADERS = frozenset((
    "host", "authorization", "content-length", "accept-encoding",
    "connection", "keep-alive", "proxy-authorization",
))


def upstream_target(path):
    """(host, port, ruta absoluta contra el upstream, ¿https?) para path.

    El perfil declara el proxy como baseURL sin ruta, así que el cliente
    siempre añade ``/v1/...``; la base del upstream ya lleva su ``/v1``
    (p. ej. ``/inference/openai/v1``): el prefijo del cliente se elimina
    siempre y la base del upstream se anteponde, para no duplicarlo.
    """
    base = urlsplit(os.environ["UPSTREAM_BASE"].rstrip("/"))
    if path.startswith("/v1"):
        path = path[len("/v1"):]
    port = base.port or (443 if base.scheme == "https" else 80)
    secure = base.scheme == "https"
    return base.hostname, port, base.path + path, secure


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in DROPPED_HEADERS}
        host, port, path, secure = upstream_target(self.path)
        factory = (http.client.HTTPSConnection if secure
                   else http.client.HTTPConnection)
        connection = factory(host, port, timeout=900)
        try:
            connection.request(self.command, path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() in ("transfer-encoding", "connection",
                                   "content-length"):
                    continue
                self.send_header(key, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                chunk = response.read1(65536)
                if not chunk:
                    break
                self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError:
            self.close_connection = True
        finally:
            connection.close()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _forward

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        ("127.0.0.1", int(os.environ.get("PROXY_PORT", "8091"))), Handler)
    server.serve_forever()
