from __future__ import annotations

import pytest

from app import _DEFAULT_JWT_SECRET, _parse_cors_origins, _validate_startup_security_config


def test_development_allows_default_jwt_secret_with_warning(capsys):
    _validate_startup_security_config(app_env="development", jwt_secret=_DEFAULT_JWT_SECRET)

    assert "using demo JWT_SECRET" in capsys.readouterr().out


def test_production_rejects_default_jwt_secret():
    with pytest.raises(RuntimeError, match="JWT_SECRET must be set"):
        _validate_startup_security_config(app_env="production", jwt_secret=_DEFAULT_JWT_SECRET)


def test_production_rejects_short_jwt_secret():
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        _validate_startup_security_config(app_env="staging", jwt_secret="too-short")


def test_production_accepts_strong_jwt_secret():
    _validate_startup_security_config(app_env="production", jwt_secret="x" * 48)


def test_parse_cors_origins_uses_csv_when_present():
    assert _parse_cors_origins("https://app.example.com, https://admin.example.com") == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_parse_cors_origins_defaults_to_local_development():
    origins = _parse_cors_origins("")

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3001" in origins
