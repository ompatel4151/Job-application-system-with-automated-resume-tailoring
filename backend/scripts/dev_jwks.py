"""Stand-in for Supabase Auth on a local machine, for load tests only.

Makes a throwaway ES256 key, serves its public half as a JWKS (the same shape
Supabase publishes), and prints a token for seed_load.LOAD_USER plus the
SUPABASE_URL to start the API with. The real token-verification code runs
unchanged; nothing here touches Supabase. Stop it with Ctrl+C.

Usage (from backend/):
  PYTHONPATH=. ../.venv/bin/python scripts/dev_jwks.py --port 8765
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.seed_load import LOAD_USER


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--hours", type=int, default=4)
    a = p.parse_args()

    key = ec.generate_private_key(ec.SECP256R1())
    url = f"http://127.0.0.1:{a.port}"
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    body = json.dumps({"keys": [{**jwk, "kid": "dev", "alg": "ES256", "use": "sig"}]}).encode()
    now = int(time.time())
    token = jwt.encode(
        {"sub": LOAD_USER, "aud": "authenticated", "iss": f"{url}/auth/v1", "role": "authenticated",
         "iat": now, "exp": now + a.hours * 3600},
        key, algorithm="ES256", headers={"kid": "dev"},
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print(f"SUPABASE_URL={url}", flush=True)
    print(f"TOKEN={token}", flush=True)
    HTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
