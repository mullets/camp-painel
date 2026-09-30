from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    CAMP_DB_PATH: str = "./camp.db"
    CAMP_QNAP_ROOT: str = "/mnt/qnap/acervos"
    CAMP_SECRET_KEY: str = "dev"
    WP_BASE_URL: str = "https://camp.arq.br"
    WP_USER: str = "camp"
    WP_APP_PASSWORD: str = ""


settings = Settings()
