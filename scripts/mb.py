"""Shared Metabase API client for provisioning scripts.

Reads .env (TS_IP, MB_ADMIN_EMAIL, MB_ADMIN_PASSWORD) from the repo root.
Uses only the Python stdlib (no pip installs on mintbox).
"""
import json
import os
import time
import urllib.request
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = {}
    with open(os.path.join(REPO_ROOT, ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


ENV = load_env()
BASE = f"http://{ENV['TS_IP']}:3000"


class Metabase:
    def __init__(self):
        self.session = None

    def request(self, method, path, body=None, timeout=120):
        req = urllib.request.Request(BASE + path, method=method)
        req.add_header("Content-Type", "application/json")
        if self.session:
            req.add_header("X-Metabase-Session", self.session)
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"{method} {path} -> {e.code}: {e.read().decode()[:2000]}") from e
        return json.loads(raw) if raw else None

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body, **kw)

    def wait_healthy(self, tries=60, delay=5):
        for _ in range(tries):
            try:
                if self.get("/api/health")["status"] == "ok":
                    return True
            except Exception:
                pass
            time.sleep(delay)
        return False

    def login(self):
        r = self.post("/api/session", {
            "username": ENV["MB_ADMIN_EMAIL"],
            "password": ENV["MB_ADMIN_PASSWORD"],
        })
        self.session = r["id"]
        return self.session

    def native_card(self, name, sql, display="scalar", viz=None,
                    collection_id=None, database_id=None):
        """Create a native-SQL question. Returns the card JSON."""
        return self.post("/api/card", {
            "name": name,
            "display": display,
            "visualization_settings": viz or {},
            "collection_id": collection_id,
            "dataset_query": {
                "type": "native",
                "database": database_id,
                "native": {"query": sql},
            },
        })

    def card_rows(self, card_id):
        """Execute a saved card, return result rows."""
        r = self.post(f"/api/card/{card_id}/query")
        return r["data"]["rows"]
