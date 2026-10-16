from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "local-demo-secret-change-before-production"


class Settings(BaseSettings):
    app_name: str = "Enterprise AI Suite API"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./enterprise_ai.db"
    approval_database_url: str = ""
    jwt_secret: str = DEFAULT_JWT_SECRET
    token_expire_minutes: int = 480
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://localhost:5174",
    ]
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "enterprise-files"
    openai_api_key: str = ""
    openai_model: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    public_app_url: str = ""
    # None = seed only in development/test. Seeding rewrites demo users, so
    # set SEED_DEMO=false when a development backend points at shared data.
    seed_demo: bool | None = None
    log_level: str = "INFO"
    login_max_failures: int = 5
    login_window_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_mode(self) -> str:
        return "local" if self.database_url.startswith("sqlite") else "postgresql"

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def ai_configured(self) -> bool:
        return bool((self.openai_api_key and self.openai_model) or self.deepseek_api_key)

    @property
    def demo_auth_enabled(self) -> bool:
        return self.app_env.lower() in {"development", "test"}

    @property
    def should_seed_demo(self) -> bool:
        if self.seed_demo is not None:
            return self.seed_demo
        return self.app_env.lower() in {"development", "test"}

    def validate_runtime_config(self) -> None:
        if self.app_env.lower() != "production":
            return
        if self.debug:
            raise RuntimeError("Production requires DEBUG=false")
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            raise RuntimeError("Production requires a random JWT_SECRET with at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
