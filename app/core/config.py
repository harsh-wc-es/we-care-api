"""
WeCare FastAPI — Centralized Configuration

Maps all 27 environment variables from the backend.
Uses Pydantic Settings for validation and .env file loading.

config/env + config/database + config/constants
"""

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All environment variables used by the application,
    verified from direct grep of env_value() / getenv() calls.
    """

    # ── Application ──
    APP_ENV: str = "production"
    APP_URL: str = "https://we-care.eu.cc/wecare"
    API_BASE_URL: str = ""
    APP_TIMEZONE: str = "Asia/Kolkata"
    APP_DEBUG: bool = False
    PORT: int = 8000
    RAILWAY_ENVIRONMENT: str = ""

    # ── JWT ──
    # Route: constants — Validated minimum 32 chars
    JWT_SECRET: str = "wecare_production_jwt_secret_key_min_32_chars_long_default"
    ACCESS_TOKEN_EXPIRE: int = 3600       # 1 hour (constant)
    REFRESH_TOKEN_EXPIRE: int = 604800    # 7 days (constant)

    # ── Database ──
    # Supports standard DB_* and Railway MySQL Plugin (MYSQLHOST, MYSQL_URL, DATABASE_URL, etc.)
    DATABASE_URL: str = ""
    MYSQL_URL: str = ""
    MYSQL_PRIVATE_URL: str = ""
    MYSQL_PUBLIC_URL: str = ""
    MYSQLHOST: str = ""
    MYSQLPORT: Optional[int] = None
    MYSQLUSER: str = ""
    MYSQLPASSWORD: str = ""
    MYSQLDATABASE: str = ""
    MYSQL_HOST: str = ""
    MYSQL_PORT: Optional[int] = None
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = ""

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = ""
    DB_DATABASE: str = ""      # Legacy alias for DB_NAME
    DB_USER: str = ""
    DB_USERNAME: str = ""      # Legacy alias for DB_USER
    DB_PASS: str = ""
    DB_PASSWORD: str = ""      # Legacy alias for DB_PASS
    DB_CHARSET: str = "utf8mb4"

    # ── SMTP ──
    # Route: helpers/mailer
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "WeCare"

    # ── Firebase ──
    # Route: helpers/firebase_fcm
    FIREBASE_SERVICE_ACCOUNT_JSON: str = ""
    FIREBASE_SERVICE_ACCOUNT_PATH: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CLIENT_EMAIL: str = ""
    FIREBASE_PRIVATE_KEY: str = ""
    FCM_SERVER_KEY: str = ""   # Legacy — helpers/notifications

    # ── Rate Limiting ──
    # Route: helpers/rate_limit
    RATE_LIMIT_ENABLED: Optional[str] = None

    # ── CORS ──
    # Route: config/cors
    CORS_ALLOWED_ORIGINS: str = ""

    # ── Uploads ──
    # .env.example
    UPLOAD_BASE_PATH: str = "uploads"
    UPLOAD_MAX_MB: int = 5

    # ── Internal ──
    WECARE_ENV_DIR: str = ""

    # ── Computed Properties ──
    # These reproduce the env_value_any() fallback behavior

    @property
    def database_name(self) -> str:
        """env_value_any(["DB_NAME", "DB_DATABASE", "MYSQLDATABASE", "MYSQL_DATABASE"], "wecare_db")"""
        return self.DB_NAME or self.DB_DATABASE or self.MYSQLDATABASE or self.MYSQL_DATABASE or "wecare_db"

    @property
    def database_user(self) -> str:
        """env_value_any(["DB_USER", "DB_USERNAME", "MYSQLUSER", "MYSQL_USER"], "root")"""
        return self.DB_USER or self.DB_USERNAME or self.MYSQLUSER or self.MYSQL_USER or "root"

    @property
    def database_password(self) -> str:
        """env_value_any(["DB_PASS", "DB_PASSWORD", "MYSQLPASSWORD", "MYSQL_PASSWORD"], "")"""
        return self.DB_PASS or self.DB_PASSWORD or self.MYSQLPASSWORD or self.MYSQL_PASSWORD or ""

    @property
    def database_url(self) -> str:
        """
        Build SQLAlchemy connection URL for MySQL+PyMySQL.
        Automatically detects:
        1. DATABASE_URL / MYSQL_URL / MYSQL_PRIVATE_URL / MYSQL_PUBLIC_URL from Railway / Cloud providers
        2. Railway MySQL plugin variables (MYSQLHOST, MYSQLPORT, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE)
        3. Standard DB_* variables (DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME)
        """
        import os
        raw_url = (
            self.DATABASE_URL
            or self.MYSQL_URL
            or self.MYSQL_PRIVATE_URL
            or self.MYSQL_PUBLIC_URL
            or os.environ.get("DATABASE_URL", "")
            or os.environ.get("MYSQL_URL", "")
            or os.environ.get("MYSQL_PRIVATE_URL", "")
            or os.environ.get("MYSQL_PUBLIC_URL", "")
        )
        if raw_url:
            raw_url = raw_url.strip()
            # Normalize scheme for SQLAlchemy pymysql driver
            if raw_url.startswith("mysql://"):
                raw_url = "mysql+pymysql://" + raw_url[len("mysql://"):]
            elif raw_url.startswith("mysql2://"):
                raw_url = "mysql+pymysql://" + raw_url[len("mysql2://"):]
            
            # Ensure utf8mb4 charset if not present
            if "?" not in raw_url:
                raw_url += f"?charset={self.DB_CHARSET}"
            elif "charset=" not in raw_url:
                raw_url += f"&charset={self.DB_CHARSET}"
            return raw_url

        host = self.MYSQLHOST or self.MYSQL_HOST or self.DB_HOST or "localhost"
        port = self.MYSQLPORT or self.MYSQL_PORT or self.DB_PORT or 3306
        user = self.database_user
        password = self.database_password
        db = self.database_name
        charset = self.DB_CHARSET
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}?charset={charset}"

    @property
    def api_base(self) -> str:
        """env_value("API_BASE_URL", $app_url . "/api/v1")"""
        if self.API_BASE_URL:
            return self.API_BASE_URL.rstrip("/")
        return f"{self.APP_URL.rstrip('/')}/api/v1"

    @property
    def smtp_from(self) -> str:
        """getenv("SMTP_FROM_EMAIL") ?: $username"""
        return self.SMTP_FROM_EMAIL or self.SMTP_USERNAME

    @property
    def rate_limit_active(self) -> bool:
        """
        Route: rate_limit behavior:
        - In "local"/"development" APP_ENV: disabled by default
        - RATE_LIMIT_ENABLED overrides if set
        """
        if self.RATE_LIMIT_ENABLED is not None:
            return self.RATE_LIMIT_ENABLED.lower() in ("true", "1", "yes")
        return self.APP_ENV not in ("local", "development")

    @property
    def cors_origins(self) -> list[str]:
        """
        Route: cors — configured + hardcoded defaults.
        Hardcoded: localhost:5173, 127.0.0.1:5173, we-care.eu.cc
        """
        configured = [
            o.strip()
            for o in self.CORS_ALLOWED_ORIGINS.split(",")
            if o.strip()
        ]
        defaults = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "https://we-care.eu.cc",
        ]
        # Add origins derived from APP_URL and API_BASE_URL (cors behavior)
        for url in [self.APP_URL, self.api_base]:
            if url:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.scheme and parsed.hostname:
                    origin = f"{parsed.scheme}://{parsed.hostname}"
                    if parsed.port:
                        origin += f":{parsed.port}"
                    defaults.append(origin)
        all_origins = configured + defaults
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for o in all_origins:
            if o and o not in seen:
                seen.add(o)
                unique.append(o)
        return unique

    @field_validator("JWT_SECRET", mode="before")
    @classmethod
    def validate_jwt_secret(cls, v: Optional[str]) -> str:
        """Validate JWT_SECRET length."""
        if not v or not str(v).strip():
            return "wecare_production_jwt_secret_key_min_32_chars_long_default"
        val = str(v).strip()
        if len(val) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return val

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for application settings."""
    return Settings()
