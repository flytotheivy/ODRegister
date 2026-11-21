"""HTTPS acceptance of the isolated synthetic preview; no credential values in output."""

import json
import re
import secrets
import sys

import httpx

from scripts.db.remote import PRIVATE, private_json, save_private
from scripts.seed.demo import did

ORIGIN = "https://od-register.vercel.app"


def main():
    checks = []

    def request(client, method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        checks.append(
            {
                "method": method,
                "path": path,
                "expected": expected,
                "actual": response.status_code,
            }
        )
        if response.status_code != expected:
            raise ValueError("Unexpected sanitized HTTP status")
        return response

    logins = private_json(PRIVATE / "logins.json")
    admin = next(a for a in logins["accounts"] if a["role"] == "ADMIN_MPALSG")
    probe_path = PRIVATE / "http-probe.json"
    if probe_path.exists():
        probe = private_json(probe_path)
    else:
        probe = {
            "email": "preview-tester@i5.agency.example.invalid",
            "password": "Preview-" + secrets.token_urlsafe(24) + "!",
        }
        save_private(probe_path, probe, exclusive=True)
    headers = {"Origin": ORIGIN}
    with (
        httpx.Client(base_url=ORIGIN, timeout=60, follow_redirects=False) as public,
        httpx.Client(base_url=ORIGIN, timeout=60, follow_redirects=False) as reviewer,
        httpx.Client(base_url=ORIGIN, timeout=60, follow_redirects=False) as member,
    ):
        root = request(public, "GET", "/")
        assert root.headers["content-type"].startswith("text/html")
        asset = re.search(r'<script[^>]*src="([^"]+)"', root.text)
        assert asset
        request(public, "GET", asset[1])
        health = request(public, "GET", "/api/health")
        assert health.json()["status"] == "ready" and "x-vercel-id" in health.headers
        assert (
            request(public, "GET", "/api/public/cycles").json()["cycles"][0]["year"]
            == 2027
        )
        request(public, "GET", "/api/public/plans?year=2027")
        feed = request(public, "GET", "/api/public/feeds/2027.json")
        assert '"email"' not in feed.text and admin["email"] not in feed.text
        request(public, "GET", "/api/admin/monitoring/2027", expected=401)
        request(public, "GET", "/.data/online-postgres/logins.json", expected=404)
        auth = request(
            reviewer,
            "POST",
            "/api/auth/login",
            headers=headers,
            json={"email": admin["email"], "password": admin["password"]},
        )
        cookie = auth.headers.get("set-cookie", "").lower()
        assert all(
            flag in cookie
            for flag in (
                "__host-l1_session",
                "secure",
                "httponly",
                "samesite=lax",
                "path=/",
            )
        )
        csrf = auth.json()["csrf_token"]
        accounts = request(
            reviewer, "GET", "/api/admin/accounts?status=all&limit=50"
        ).json()["items"]
        found = next((a for a in accounts if a["email"] == probe["email"]), None)
        created = found is None
        if created:
            payload = {
                **probe,
                "institution_id": str(did("i5")),
                "name": "SYNTHETIC remote approval test",
            }
            receipt = request(
                public,
                "POST",
                "/api/access/requests",
                headers=headers,
                json=payload,
                expected=201,
            )
            assert receipt.json()["status"] == "pending"
            request(
                member,
                "POST",
                "/api/auth/login",
                headers=headers,
                json=probe,
                expected=401,
            )
            accounts = request(
                reviewer, "GET", "/api/admin/accounts?status=pending&limit=50"
            ).json()["items"]
            found = next(a for a in accounts if a["email"] == probe["email"])
        if found["status"] == "pending":
            review = {
                "decision": "approved",
                "correspondence_checked": True,
                "approval_reference": "SYNTHETIC P6-02 remote acceptance; not official correspondence",
            }
            path = "/api/admin/accounts/" + found["id"] + "/review"
            request(reviewer, "POST", path, headers=headers, json=review, expected=403)
            request(
                reviewer,
                "POST",
                path,
                headers={**headers, "X-CSRF-Token": csrf},
                json=review,
            )
        elif found["status"] != "approved":
            raise ValueError("Existing probe account cannot be adopted")
        logged_in = request(
            member, "POST", "/api/auth/login", headers=headers, json=probe
        )
        assert logged_in.json()["role"] == "institution_user"
        member_csrf = logged_in.json()["csrf_token"]
        request(member, "GET", "/api/auth/me")
        request(member, "GET", "/api/my-plans")
        request(member, "GET", "/api/admin/accounts", expected=403)
        request(
            member,
            "POST",
            "/api/auth/logout",
            headers={
                "Origin": "https://wrong.example.invalid",
                "X-CSRF-Token": member_csrf,
            },
            json={},
            expected=403,
        )
        request(
            member,
            "POST",
            "/api/auth/logout",
            headers={**headers, "X-CSRF-Token": member_csrf},
            json={},
        )
        request(member, "GET", "/api/auth/me", expected=401)
        request(
            reviewer,
            "POST",
            "/api/auth/logout",
            headers={**headers, "X-CSRF-Token": csrf},
            json={},
        )
    report = {
        "status": "PASS",
        "origin": ORIGIN,
        "checks": checks,
        "count": len(checks),
        "flow": "HTTPS request -> pending login denied -> admin approval with CSRF -> member login -> logout",
        "secure_host_cookie": True,
        "csrf_enforced": True,
        "origin_enforced": True,
        "local_api_or_database_used": False,
        "actual_mac_power_off_test": False,
        "synthetic_probe_account_retained": True,
        "probe_account_created_this_run": created,
        "private_passwords_and_tokens_reported": False,
    }
    (PRIVATE / "remote-http-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - no driver/HTTP payload or credential diagnostics
        print(
            json.dumps({"status": "FAILED", "error_type": type(exc).__name__}),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
