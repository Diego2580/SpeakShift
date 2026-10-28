from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración centralizada, cargada desde variables de entorno."""

    # --- Base de datos ---
    DATABASE_URL: str
    APP_ENV: str = "development"

    # --- LLM / OpenRouter ---
    # La key se valida en tiempo de uso (no al arrancar) para que la API
    # y el healthcheck sigan funcionando aunque aún no esté configurada.
    OPENROUTER_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


settings = Settings()