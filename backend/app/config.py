from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"

    DATABASE_URL: str = "mysql+asyncmy://app_user:password@mysql:3306/qna"
    REDIS_URL: str = "redis://redis:6379/0"

    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""

    # Required for /auth/oauth2-callback to accept X-Auth-Request-* identity
    # headers. Unset (the default) means the callback refuses every request —
    # fail closed, since those headers are otherwise a trivial impersonation
    # vector for anyone with network access to this service. Set this to a
    # random secret and configure the same value in the OAuth2 reverse proxy
    # sitting in front of this service, which must strip any client-supplied
    # copy of this header and set its own.
    OAUTH2_PROXY_SHARED_SECRET: str = ""

    CORS_ORIGINS: str = (
        "http://localhost:8080,http://localhost:8000,http://localhost:5173"
    )
    FRONTEND_URL: str = "http://localhost:8080"

    # Bootstrap — set once to create the first admin; ignored once an admin exists
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""

    # Course grader account — base64 of a bcrypt hash published by course staff.
    # When set, startup keeps an ADMIN user named "grader" with this hash, so
    # staff can sign in to your deployment without you sharing a password.
    GRADER_PASSWORD_HASH: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
