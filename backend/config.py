from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/naar_monitor"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Claude / production
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    USE_CLAUDE: bool = True
    PRODUCTION_MODE: bool = False
    DEMO_MODE: bool = True

    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    MIN_MATCH_CONFIDENCE: float = 0.75
    USE_EMBEDDINGS: bool = False

    BRIGHTDATA_PROXY: str = ""
    SCRAPERAPI_KEY: str = ""
    ZYTE_API_KEY: str = ""

    SENDGRID_API_KEY: str = ""
    ALERT_EMAIL_FROM: str = "alerts@naar.io"
    ALERT_EMAIL_TO: str = "pricing@naar.io"
    SLACK_WEBHOOK_URL: str = ""

    MAX_PRICE_DEVIATION_PCT: float = 5.0
    CRITICAL_DEVIATION_PCT: float = 20.0

    DASHBOARD_URL: str = "http://localhost:3000"

    # Naar shop catalog (source of truth for price parity)
    NAAR_BASE_URL: str = "https://naar.io"
    NAAR_SHOP_URL: str = "https://naar.io/shop"
    NAAR_CATALOG_API: str = ""

    @model_validator(mode="after")
    def apply_production_defaults(self) -> "Settings":
        if self.PRODUCTION_MODE and self.ANTHROPIC_API_KEY:
            object.__setattr__(self, "DEMO_MODE", False)
        return self

    @property
    def effective_database_url(self) -> str:
        if "sqlite" in self.DATABASE_URL:
            return self.DATABASE_URL
        # Local dev: SQLite for demo and for live mode without Postgres.
        use_sqlite = self.DEMO_MODE or self.is_production
        if use_sqlite and self.DATABASE_URL.startswith("postgresql"):
            db_name = "naar_monitor_demo.db" if self.DEMO_MODE else "naar_monitor_live.db"
            db_path = _ROOT / "data" / db_name
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{db_path}"
        return self.DATABASE_URL

    @property
    def is_production(self) -> bool:
        return self.PRODUCTION_MODE and not self.DEMO_MODE and bool(self.ANTHROPIC_API_KEY)

    @property
    def claude_enabled(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY) and self.USE_CLAUDE


settings = Settings()
