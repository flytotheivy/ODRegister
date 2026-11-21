"""System-CA portability must preserve TLS identity verification and explicit trust."""

from types import SimpleNamespace

from sqlalchemy.engine import make_url

from backend import connections


def url(ca="system"):
    return make_url(
        "postgresql+psycopg://app:synthetic-only@db.example.invalid/preview"
    ).set(
        query={
            "sslrootcert": ca,
            "sslmode": "verify-full",
            "channel_binding": "require",
        }
    )


def test_system_ca_resolves_available_os_bundle_without_weakening_tls(monkeypatch):
    monkeypatch.setattr(
        connections.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=None),
    )
    monkeypatch.setattr(
        connections.Path,
        "is_file",
        lambda p: str(p) == "/etc/ssl/certs/ca-certificates.crt",
    )
    resolved = connections.portable_certificate_url(url())
    assert resolved.query["sslrootcert"] == "/etc/ssl/certs/ca-certificates.crt"
    assert resolved.query["sslmode"] == "verify-full"
    assert resolved.query["channel_binding"] == "require"
    assert resolved.host == url().host and resolved.username == "app"


def test_explicit_operator_certificate_is_preserved():
    original = url("/private/operator-ca.pem")
    assert connections.portable_certificate_url(original) is original


def test_absent_local_bundle_keeps_system_verification(monkeypatch):
    monkeypatch.setattr(
        connections.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=None),
    )
    monkeypatch.setattr(connections.Path, "is_file", lambda p: False)
    original = url()
    assert connections.portable_certificate_url(original) is original


def test_system_resolution_cannot_weaken_hostname_verification(monkeypatch):
    monkeypatch.setattr(
        connections.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile="/system-ca.pem"),
    )
    monkeypatch.setattr(connections.Path, "is_file", lambda p: True)
    original = url().set(query={"sslrootcert": "system", "sslmode": "require"})
    assert (
        connections.portable_certificate_url(original).query["sslmode"] == "verify-full"
    )
