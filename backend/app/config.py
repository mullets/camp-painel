from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV = Path(__file__).resolve().parents[1] / ".env"   # sempre backend/.env, de onde quer que rode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV), env_prefix="", extra="ignore")

    CAMP_DB_PATH: str = "./camp.db"
    CAMP_QNAP_ROOT: str = "/mnt/qnap/acervos"
    CAMP_SECRET_KEY: str = "dev"
    WP_BASE_URL: str = "https://camp.arq.br"
    WP_USER: str = "camp"
    WP_APP_PASSWORD: str = ""
    # True quando o acesso é por HTTPS (túnel Cloudflare). False só em rede local por http://.
    CAMP_COOKIE_SECURE: bool = True


settings = Settings()

# Caminho relativo do banco é SEMPRE relativo à pasta backend/, não à pasta atual.
if not Path(settings.CAMP_DB_PATH).is_absolute():
    settings.CAMP_DB_PATH = str((ENV.parent / settings.CAMP_DB_PATH).resolve())
