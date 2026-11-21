"""Credential boundary and non-destructive resume checks; never connects to any DB."""

import pytest

from scripts.db import remote


def config_at(path, *, resource="odregister-preview", driver="postgresql"):
    path.mkdir(exist_ok=True)
    value = {
        "resource": resource,
        "provider": "Neon",
        "connections": {
            "DATABASE_URL": f"{driver}://platform:synthetic-only-password@ep-fixture-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require",
            "DATABASE_URL_UNPOOLED": f"{driver}://platform:synthetic-only-password@ep-fixture.eu-central-1.aws.neon.tech/neondb?sslmode=require",
        },
    }
    remote.save_private(path / "provider.json", value, exclusive=True)
    return value


def test_private_file_permission_and_symlink_rejected(tmp_path):
    source = tmp_path / "source.json"
    remote.save_private(source, {"secret": "synthetic"})
    source.chmod(0o644)
    with pytest.raises(ValueError):
        remote.private_json(source)
    source.chmod(0o600)
    link = tmp_path / "alias.json"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        remote.private_json(link)


@pytest.mark.parametrize("changes", [{"resource": "production"}, {"driver": "sqlite"}])
def test_wrong_resource_or_driver_rejected_before_network(
    tmp_path, monkeypatch, changes
):
    monkeypatch.setattr(remote, "PRIVATE", tmp_path)
    config_at(tmp_path, **changes)
    with pytest.raises(ValueError):
        remote.load()


def test_resume_preserves_credentials_and_refuses_changed_destination(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(remote, "PRIVATE", tmp_path)
    cfg = config_at(tmp_path)
    before = remote.state()
    assert remote.state() == before
    cfg["connections"]["DATABASE_URL_UNPOOLED"] = cfg["connections"][
        "DATABASE_URL_UNPOOLED"
    ].replace("ep-fixture.", "ep-different.")
    remote.save_private(tmp_path / "provider.json", cfg)
    with pytest.raises(ValueError):
        remote.state()
    assert remote.private_json(tmp_path / "roles.json") == before


def test_runtime_url_replaces_platform_owner_and_enforces_tls(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "PRIVATE", tmp_path)
    config_at(tmp_path)
    runtime = remote.role_url("app", pooled=True)
    assert runtime.username == "layer1_preview_app"
    assert "-pooler" in runtime.host
    assert runtime.query["sslmode"] == "verify-full"
    assert runtime.password != "synthetic-only-password"
    assert (tmp_path / "roles.json").stat().st_mode & 0o077 == 0


def test_remote_install_never_exposes_ownership_privileges_to_app():
    assert set(remote.PRIVILEGES) == {t.name for t in remote.metadata.tables.values()}
    assert remote.PRIVILEGES["audit_event"] == ("SELECT", "INSERT")
    assert remote.PRIVILEGES["plan_revision"] == ("SELECT", "INSERT")
    assert all("TRUNCATE" not in grants for grants in remote.PRIVILEGES.values())


def test_exported_runtime_uses_direct_app_role_not_provider_pooler(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(remote, "PRIVATE", tmp_path)
    config_at(tmp_path)
    cfg = remote.runtime_configuration()
    url = remote.make_url(cfg["DATABASE_URL"])
    assert "-pooler" not in url.host
    assert url.username == "layer1_preview_app"
    assert url.query["sslmode"] == "verify-full"
    assert cfg["L1_DB_POOL_MODE"] == "null"
    assert cfg["L1_CONNECT_TIMEOUT"] == 5
    assert cfg["L1_APP_ORIGIN"] is None


def test_private_publish_never_overwrites_existing_credentials_in_exclusive_mode(
    tmp_path,
):
    path = tmp_path / "secret.json"
    remote.save_private(path, {"credential": "original"}, exclusive=True)
    with pytest.raises(FileExistsError):
        remote.save_private(path, {"credential": "replacement"}, exclusive=True)
    assert remote.private_json(path) == {"credential": "original"}
    assert list(tmp_path.glob(".private-*")) == []
