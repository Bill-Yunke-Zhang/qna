"""
Unit tests for the rate-limit key function.

_rate_limit_key returns a fresh random key on every call whenever
APP_ENV=development (so rate limiting is effectively a no-op locally) and a
stable per-client key otherwise. That dev bypass needs to actually be scoped
to development — if it silently applied in any other environment, the
/auth/login and /auth/exchange-temp rate limits (the only brute-force
protection this app has) would do nothing.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def test_development_mode_returns_a_fresh_key_every_call(monkeypatch):
    from app.common.rate_limit import _rate_limit_key
    from app.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "development")
    request = MagicMock()

    key1 = _rate_limit_key(request)
    key2 = _rate_limit_key(request)

    assert key1 != key2  # a new random key every time == rate limiting never fires


def test_non_development_mode_uses_a_stable_key_per_client(monkeypatch):
    from app.common.rate_limit import _rate_limit_key
    from app.config import settings
    from slowapi.util import get_remote_address

    monkeypatch.setattr(settings, "APP_ENV", "production")
    request = MagicMock()
    request.client.host = "203.0.113.5"
    request.headers = {}

    key1 = _rate_limit_key(request)
    key2 = _rate_limit_key(request)

    assert key1 == key2 == get_remote_address(request)
