"""Profile resolution: env override and profiles.ini parsing."""

import pytest

from thunderbird_mcp import config


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    monkeypatch.delenv("THUNDERBIRD_PROFILE", raising=False)
    config.profile_dir.cache_clear()
    yield
    config.profile_dir.cache_clear()


def test_env_override_wins(tmp_path, monkeypatch):
    prof = tmp_path / "my-profile"
    prof.mkdir()
    monkeypatch.setenv("THUNDERBIRD_PROFILE", str(prof))
    assert config.profile_dir() == prof


def test_env_override_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("THUNDERBIRD_PROFILE", str(tmp_path / "nope"))
    with pytest.raises(FileNotFoundError):
        config.profile_dir()


def _write_ini(root, body):
    root.mkdir(parents=True, exist_ok=True)
    (root / "profiles.ini").write_text(body, encoding="utf-8")


def test_install_default_preferred(tmp_path):
    prof = tmp_path / "Profiles" / "abc.default-release"
    prof.mkdir(parents=True)
    _write_ini(
        tmp_path,
        "[Install123]\n"
        "Default=Profiles/abc.default-release\n\n"
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        "Path=Profiles/abc.default-release\n",
    )
    assert config._profile_from_ini(tmp_path) == prof


def test_profile_default_flag_fallback(tmp_path):
    prof = tmp_path / "Profiles" / "xyz.default"
    prof.mkdir(parents=True)
    _write_ini(
        tmp_path,
        "[Profile0]\nIsRelative=1\nPath=Profiles/other\n\n"
        "[Profile1]\nIsRelative=1\nPath=Profiles/xyz.default\nDefault=1\n",
    )
    assert config._profile_from_ini(tmp_path) == prof


def test_no_ini_returns_none(tmp_path):
    assert config._profile_from_ini(tmp_path) is None
