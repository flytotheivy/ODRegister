"""Exact institution-domain policy. No DNS, SMTP, suffix allowlist or mail proof."""

import re
import unicodedata

# Explicit input blocklist; absence never establishes government affiliation.
PRIVATE_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.co.jp",
        "ymail.com",
        "outlook.com",
        "hotmail.com",
        "hotmail.co.uk",
        "live.com",
        "msn.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "mail.com",
        "gmx.com",
        "gmx.de",
        "proton.me",
        "protonmail.com",
        "yandex.com",
        "yandex.ru",
        "mail.ru",
        "qq.com",
        "163.com",
    }
)
LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")


def normalize_domain(value):
    if not value or any(c.isspace() for c in value) or value.endswith("."):
        raise ValueError("invalid_domain")
    # Builtin IDNA2003 is used consistently; reject mapped separators/characters.
    try:
        result = value.lower().encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("invalid_domain") from None
    if len(result) > 253 or "." not in result:
        raise ValueError("invalid_domain")
    labels = result.split(".")
    if any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("invalid_domain")
    if value.count(".") != result.count("."):
        raise ValueError("invalid_domain")
    return result


def normalize_email(value):
    value = value.strip()
    if len(value) > 254 or value.count("@") != 1:
        raise ValueError("invalid_email")
    local, domain = value.split("@")
    if (
        not LOCAL.fullmatch(local)
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise ValueError("invalid_email")
    normalized = local.lower() + "@" + normalize_domain(domain)
    if len(normalized) > 254:
        raise ValueError("invalid_email")
    return normalized


def clean_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 150 or any(
        unicodedata.category(c).startswith("C") for c in value
    ):
        raise ValueError("invalid_name")
    return value


def private_domain(domain):
    return any(domain == d or domain.endswith("." + d) for d in PRIVATE_DOMAINS)
