from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración centralizada, cargada desde variables de entorno."""
    DATABASE_URL: str
    APP_ENV: str = "development"


settings = Settings()