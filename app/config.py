import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Supabase (opcional, solo para produccion)
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")

    # App
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    app_name: str = "CAÑAS"

    # Database
    raw_database_url: str = os.getenv("DATABASE_URL", "")

    @property
    def database_url(self) -> str:
        if self.raw_database_url:
            if self.raw_database_url.startswith("postgresql://"):
                return self.raw_database_url.replace(
                    "postgresql://", "postgresql+asyncpg://", 1
                )
            if "+asyncpg" in self.raw_database_url:
                return self.raw_database_url
        return "sqlite+aiosqlite:///./canas.db"

    # Wger
    wger_api_url: str = "https://wger.de/api/v2"


settings = Settings()
