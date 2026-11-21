"""13 baseline themes, 39 draft labels; production review is still external."""

from scripts.db.common import DEV
from scripts.seed.core import (
    ImportRejected,
    identity,
    insert_immutable,
    load_json,
    nonproduction,
)

CODES = (
    "AGRI",
    "ECON",
    "EDUC",
    "ENER",
    "ENVI",
    "GOVE",
    "HEAL",
    "INTR",
    "JUST",
    "SOCI",
    "REGI",
    "TECH",
    "TRAN",
)
LOCALES = {"en", "sr-Latn", "sr-Cyrl"}


def catalog():
    data, sha = load_json(DEV / "reference/themes.v1.json")
    if data.get("format") != "layer1-themes/1" or [
        t["code"] for t in data["themes"]
    ] != list(CODES):
        raise ImportRejected("theme_catalog_invalid")
    for t in data["themes"]:
        if (
            t["uri"]
            != "http://publications.europa.eu/resource/authority/data-theme/"
            + t["code"]
            or set(t["labels"]) != LOCALES
            or not all(isinstance(v, str) and v.strip() for v in t["labels"].values())
        ):
            raise ImportRejected("theme_labels_or_uri_invalid")
    return data, sha


def install(conn, *, deployment="development", apply=False):
    nonproduction(conn, deployment)
    data, sha = catalog()
    with conn.transaction():
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('layer1-reference-import'))"
        )
        for theme in data["themes"]:
            tid = identity("theme:" + theme["code"])
            if apply:
                insert_immutable(
                    conn,
                    "theme",
                    {"id": tid, "code": theme["code"], "uri": theme["uri"]},
                )
                for locale, label in theme["labels"].items():
                    insert_immutable(
                        conn,
                        "theme_translation",
                        {"theme_id": tid, "locale": locale, "label": label},
                        ("theme_id", "locale"),
                    )
    return {
        "status": "applied" if apply else "validated",
        "themes": 13,
        "translations": 39,
        "sha256": sha,
        "production_approved": False,
        "translation_status": data["translation_status"],
    }
