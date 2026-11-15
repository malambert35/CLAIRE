from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAIRE_")
    database_url: str = "postgresql+psycopg://claire@claire-db/claire"
    database_url_file: Path | None = None
    origin: str = "https://localhost"
    secure_cookies: bool = True
    data_dir: Path = Path("data/archive")
    static_dir: Path = Path("/app/static")
    session_hours: int = 12

    def db_url(self):
        return self.database_url_file.read_text().strip() if self.database_url_file else self.database_url
