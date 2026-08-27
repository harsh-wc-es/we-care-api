"""
STEP 15b: Test configuration loading and validation.
"""

import pytest


def test_settings_loads_defaults(settings):
    """Settings must load with sensible defaults."""
    assert settings.APP_ENV == "local"
    assert settings.APP_TIMEZONE == "Asia/Kolkata"
    assert settings.DB_CHARSET == "utf8mb4"
    assert settings.UPLOAD_MAX_MB == 5


def test_database_url_format(settings):
    """Database URL must be valid mysql+pymysql format."""
    url = settings.database_url
    assert url.startswith("mysql+pymysql://")
    assert "utf8mb4" in url
    assert "wecare_test_db" in url


def test_legacy_alias_db_name():
    """DB_DATABASE must work as alias for DB_NAME (compatibility)."""
    from app.core.config import Settings
    s = Settings(
        JWT_SECRET="test_secret_key_that_is_at_least_32_characters_long",
        DB_NAME="",
        DB_DATABASE="legacy_db",
    )
    assert s.database_name == "legacy_db"


def test_legacy_alias_db_user():
    """DB_USERNAME must work as alias for DB_USER (compatibility)."""
    from app.core.config import Settings
    s = Settings(
        JWT_SECRET="test_secret_key_that_is_at_least_32_characters_long",
        DB_USER="",
        DB_USERNAME="legacy_user",
    )
    assert s.database_user == "legacy_user"


def test_legacy_alias_db_pass():
    """DB_PASSWORD must work as alias for DB_PASS (compatibility)."""
    from app.core.config import Settings
    s = Settings(
        JWT_SECRET="test_secret_key_that_is_at_least_32_characters_long",
        DB_PASS="",
        DB_PASSWORD="legacy_pass",
    )
    assert s.database_password == "legacy_pass"


def test_cors_origins_include_defaults(settings):
    """CORS origins must include hardcoded defaults."""
    origins = settings.cors_origins
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "https://we-care.eu.cc" in origins


def test_rate_limit_disabled_in_local(settings):
    """Rate limiting disabled in local env by default (behavior)."""
    assert settings.rate_limit_active is False


def test_rate_limit_enabled_in_production():
    """Rate limiting enabled in production when not explicitly set."""
    from app.core.config import Settings
    s = Settings(
        APP_ENV="production",
        JWT_SECRET="test_secret_key_that_is_at_least_32_characters_long",
        RATE_LIMIT_ENABLED=None,
    )
    assert s.rate_limit_active is True


def test_jwt_secret_validation():
    """JWT_SECRET < 32 chars must raise validation error."""
    from app.core.config import Settings
    with pytest.raises(Exception):
        Settings(JWT_SECRET="too_short")


def test_api_base_url_fallback(settings):
    """api_base must construct from APP_URL when API_BASE_URL is empty."""
    assert settings.api_base.endswith("/api/v1")
