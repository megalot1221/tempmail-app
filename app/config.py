from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TempMail App"
    app_host: str = "127.0.0.1"
    app_port: int = 8080

    tempmail_api: str
    database_url: str

    jwt_secret: str
    jwt_expire_minutes: int = 1440

    provisioner_url: str
    provisioner_token: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
