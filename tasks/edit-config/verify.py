"""Hidden checks for edit-config: exact target values, nothing else touched."""

import sys
import tomllib
from pathlib import Path

ws = Path.cwd()
ORIGINAL = Path(__file__).resolve().parent / "workspace"


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


try:
    cfg = tomllib.loads((ws / "config/app.toml").read_text(encoding="utf-8"))
except Exception as exc:  # noqa: BLE001
    fail(f"config/app.toml does not parse: {exc}")
want = {
    "server": {"host": "127.0.0.1", "port": 8081, "workers": 4},
    "logging": {"level": "debug", "format": "json"},
    "cors": {
        "allowed_origins": ["https://example.com", "https://example.org"],
        "allow_credentials": False,
    },
}
if cfg != want:
    fail(f"config/app.toml values differ from the request:\n got  {cfg}\n want {want}")
text = (ws / "config/app.toml").read_text(encoding="utf-8")
if "# Local development settings. Production values live in app.prod.toml." not in text:
    fail("the header comment in config/app.toml was removed or changed")
prod_now = (ws / "config/app.prod.toml").read_bytes()
if prod_now != (ORIGINAL / "config/app.prod.toml").read_bytes():
    fail("config/app.prod.toml was modified")
print("PASS")
