from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Onedo bot"
    app_domain: str = "onedo-bot.1doprojects.ir"
    secret_key: str = "change-me-onedo-bot-secret-key-32chars"
    admin_api_token: str = "onedo-admin-api-token-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    database_url: str = "postgresql+psycopg2://onedo:onedo_secret@db:5432/onedo_bot"
    openai_compatible_base_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: str = ""
    openai_compatible_model: str = "gpt-4o-mini"
    default_admin_email: str = "admin@onedo.local"
    default_admin_password: str = "Admin123!"
    cors_origins: str = "*"
    browser_http_url: str = "http://browser:3000"
    browser_ws_url: str = "ws://browser:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
