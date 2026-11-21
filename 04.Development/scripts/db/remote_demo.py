"""Explicit synthetic seed for the named isolated remote preview. Never a production import."""

import json
import secrets
import sys

from sqlalchemy import insert, text, update

from backend.models import account, metadata
from backend.passwords import encode_password, verify_password
from scripts.db.remote import (
    PRIVATE,
    private_json,
    role,
    role_engine,
    save_private,
    state,
)
from scripts.seed.demo import did, rows


def install():
    st = state()
    marker = PRIVATE / "demo-state.json"
    logins_path = PRIVATE / "logins.json"
    if marker.exists():
        saved = private_json(marker)
        if saved["identity"] != st["identity"] or not saved["installed"]:
            raise ValueError("Unrecognised preview fixture state")
        return {"status": "PRESERVED", "reset": False, "credentials_rotated": False}
    data = rows()  # Immutable synthetic source; does not read the manual DB.
    if logins_path.exists():
        logins = private_json(logins_path)
        if logins["identity"] != st["identity"]:
            raise ValueError("Preview identity changed")
    else:
        logins = {
            "identity": st["identity"],
            "accounts": [
                {
                    "email": a["email"],
                    "role": a["role"],
                    "password": "Preview-" + secrets.token_urlsafe(24) + "!",
                }
                for a in data["account"]
                if a["status"] == "approved"
            ],
        }
        save_private(logins_path, logins, exclusive=True)
    eng = role_engine("migrator")
    try:
        with eng.begin() as c:
            c.execute(text("SET ROLE " + role("owner")))
            c.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext('odregister-preview-demo'))"
                )
            )
            server_marker = c.execute(
                text(
                    "SELECT obj_description('layer1_migration'::regnamespace,'pg_namespace')"
                )
            ).scalar_one()
            if server_marker != st["marker"]:
                raise ValueError("Unknown remote database")
            already = c.execute(
                text("SELECT 1 FROM layer1.audit_event WHERE id=:id"),
                {"id": did("audit")},
            ).scalar_one_or_none()
            if already:
                # Recover after commit/file-write interruption; never reseed or reset passwords.
                for a in logins["accounts"]:
                    stored = c.execute(
                        text(
                            "SELECT password_hash FROM layer1.account WHERE normalized_email=:email"
                        ),
                        {"email": a["email"]},
                    ).scalar_one()
                    if not verify_password(a["password"], stored):
                        raise ValueError("Existing preview credentials differ")
            else:
                if any(
                    c.execute(
                        text("SELECT EXISTS(SELECT 1 FROM layer1." + name + ")")
                    ).scalar_one()
                    for name in data
                ):
                    raise ValueError(
                        "Remote synthetic seed requires empty business tables"
                    )
                order = [
                    "theme",
                    "theme_translation",
                    "institution_register_version",
                    "institution",
                    "cycle",
                    "cycle_institution",
                ]
                for name in order:
                    c.execute(insert(metadata.tables["layer1." + name]), data[name])
                c.execute(insert(account), data["account"][:2])
                c.execute(
                    insert(metadata.tables["layer1.institution_email_domain"]),
                    data["institution_email_domain"],
                )
                c.execute(insert(account), data["account"][2:])
                for name in [
                    "cycle_theme",
                    "plan",
                    "planned_dataset",
                    "plan_revision",
                    "audit_event",
                ]:
                    c.execute(insert(metadata.tables["layer1." + name]), data[name])
                for a in logins["accounts"]:
                    c.execute(
                        update(account)
                        .where(account.c.normalized_email == a["email"])
                        .values(password_hash=encode_password(a["password"]))
                    )
            summary = {
                "status": "PASS",
                "scope": "Synthetic preview only",
                "institutions": 7,
                "themes": 13,
                "plans": 3,
                "items": 3,
                "usable_seed_logins": len(logins["accounts"]),
                "manual_data_copied": False,
                "credential_values_reported": False,
                "business_rows": sum(
                    c.execute(text("SELECT count(*) FROM layer1." + name)).scalar_one()
                    for name in data
                ),
            }
            if summary["business_rows"] != 105:
                raise ValueError("Unexpected initial preview row inventory")
    finally:
        eng.dispose()
    save_private(
        marker, {"identity": st["identity"], "installed": True, "fixture": "demo-v1"}
    )
    (PRIVATE / "demo-verification.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    lines = [
        "ODRegister temporary synthetic preview login accounts",
        "Private: do not commit or forward",
        "",
    ]
    for a in logins["accounts"]:
        lines += [a["role"], a["email"], a["password"], ""]
    path = PRIVATE / "LOGIN_PRIVATE.txt"
    path.write_text("\n".join(lines))
    path.chmod(0o600)
    return summary


if __name__ == "__main__":
    try:
        print(json.dumps(install()))
    except Exception as exc:  # noqa: BLE001 - redact credentials and SQL diagnostics
        print(
            json.dumps({"status": "FAILED", "error_type": type(exc).__name__}),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
