"""The exposure check: does a host keep its edges shut against a stranger? Phase 1's gate (docs/cast-review.md).

    python tools/exposure.py https://thespis-production.up.railway.app
    python tools/exposure.py http://localhost:8000

Every request is one anyone could send: no admin token, no game played. Prints each check and exits 1 if any fails.
"""

from __future__ import annotations

import argparse
import sys

import httpx

STRANGER = "https://elsewhere.example"
SECRETS = ("/.env", "/.git/config", "/thespis.sqlite", "/data/thespis.sqlite", "/manor.sqlite", "/requirements.txt")


def checks(client) -> list[tuple[str, bool, str]]:
    """(what, passed, what came back) for every check. `client` is an httpx.Client or a TestClient for the host."""
    out: list[tuple[str, bool, str]] = []

    def check(what: str, passed: bool, detail: object = "") -> None:
        out.append((what, bool(passed), str(detail)))

    r = client.get("/health")
    check("/health answers", r.status_code == 200 and r.json() == {"ok": True}, r.status_code)
    for headers, who in (({}, "no token"), ({"Authorization": "Bearer not-the-token"}, "a wrong token")):
        r = client.get("/dev/calls", headers=headers)
        check(f"the call log refuses {who}", r.status_code in (401, 404), r.status_code)
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path)
        check(f"{path} isn't served", r.status_code == 404, r.status_code)
    r = client.options("/act", headers={"Origin": STRANGER, "Access-Control-Request-Method": "POST"})
    check("another origin can't call the API", "access-control-allow-origin" not in r.headers,
          r.headers.get("access-control-allow-origin", "no CORS header"))
    r = client.get("/", headers={"Origin": STRANGER})
    check("another origin can't read the page", "access-control-allow-origin" not in r.headers,
          r.headers.get("access-control-allow-origin", "no CORS header"))
    check("pages are sent nosniff", r.headers.get("x-content-type-options") == "nosniff",
          r.headers.get("x-content-type-options", "missing"))
    check("pages carry a referrer policy", "referrer-policy" in r.headers, r.headers.get("referrer-policy", "missing"))
    r = client.post("/act", content=b"x" * (100 * 1024), headers={"Content-Type": "application/json"})
    check("a 100 KiB body is refused", r.status_code == 413, r.status_code)
    for path in SECRETS:
        r = client.get(path)
        check(f"{path} isn't served", r.status_code != 200, r.status_code)
    r = client.post("/act", content=b"{not json", headers={"Content-Type": "application/json", "X-Session": "nobody"})
    check("a malformed request gets a JSON error and no traceback",
          r.status_code == 400 and r.headers.get("content-type", "").startswith("application/json")
          and "Traceback" not in r.text, r.status_code)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("host")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.host.rstrip("/"), timeout=30, follow_redirects=False) as client:
        results = checks(client)
    for what, passed, detail in results:
        print(f"{'ok  ' if passed else 'FAIL'} {what} ({detail})")
    failed = sum(not passed for _, passed, _ in results)
    print(f"{len(results) - failed} of {len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
