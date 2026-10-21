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

    # RAG services (docs/design-rag.md §5.1). Defaults are the Compose
    # service names on qna_network.
    OLLAMA_URL: str = "http://ollama:11434"
    INFINITY_URL: str = "http://infinity:7997"
    CHROMA_URL: str = "http://chromadb:8000"
    # Timeout for embedding, model-list and vector-store calls. Generation has
    # its own deadline per call (§5.3).
    RAG_SERVICE_TIMEOUT_S: float = 60.0
    # Texts per Infinity request; match Infinity's own INFINITY_BATCH_SIZE.
    INFINITY_BATCH_SIZE: int = 16

    # MiniLM's word-piece tokenizer, which counts chunk sizes in every profile
    # (§6.2). Baked into the image outside the /app bind mount.
    CHUNK_TOKENIZER_PATH: str = "/opt/tokenizers/minilm/tokenizer.json"

    # Fetching syllabus and schedule pages (§7.4, §8).
    WEB_FETCH_TIMEOUT_S: float = 20.0
    WEB_FETCH_MAX_BYTES: int = 5_000_000
    WEB_FETCH_MAX_REDIRECTS: int = 5

    # Uploads (§7.2). The total matches nginx's client_max_body_size (50m) on
    # /api/. Zip limits are counted while decompressing, never taken from the
    # sizes the zip declares, so a zip bomb can't exhaust memory.
    UPLOAD_MAX_BYTES: int = 50 * 1024 * 1024
    UPLOAD_MAX_FILES: int = 500
    UPLOAD_MAX_ENTRY_BYTES: int = 50 * 1024 * 1024
    UPLOAD_MAX_UNCOMPRESSED_BYTES: int = 200 * 1024 * 1024

    # The ingestion profile live answering uses (§6.3); also the default for
    # a newly registered source.
    RAG_LIVE_PROFILE: str = "sliding-window"

    # The only host repository URLs may point at, and the only host the
    # GitLab access token is ever sent to (§8).
    GITLAB_HOST: str = "git.doit.wisc.edu"

    # After a sync switches to its new chunks, how long to keep the old ones
    # so queries that read the previous sync_id can finish (§7.3).
    CLEANUP_GRACE_S: float = 30.0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


settings = Settings()
