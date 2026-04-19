from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    openai_api_key: str
    openai_model: str = "gpt-4o"
    libreoffice_path: str | None = None
    templates_dir: str = "templates"
    generated_dir: str = "storage/generated"
    temp_dir: str = "storage/temp"
    sellers_path: str = "storage/sellers.json"
    stamps_dir: str = "storage/stamps"
    signatures_dir: str = "storage/signatures"
    gliner_model_id: str = "urchade/gliner_medium-v2.1"
    pdf_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
