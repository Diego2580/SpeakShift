from pydantic_settings import BaseSettings

# Clave SOLO para desarrollo. En producción debe venir del entorno (.env).
DEFAULT_DEV_SECRET_KEY = "tu-clave-secreta-de-desarrollo"


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
    # Modelos de respaldo separados por coma (opcional): "modelo-a,modelo-b"
    LLM_FALLBACK_MODELS: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # --- Autenticación JWT ---
    SECRET_KEY: str = DEFAULT_DEV_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7


settings = Settings()

# Protección: nunca arrancar en producción con la clave de desarrollo
if settings.APP_ENV.lower() == "production" and settings.SECRET_KEY == DEFAULT_DEV_SECRET_KEY:
    raise RuntimeError("SECRET_KEY por defecto detectada en producción: define una clave segura en el entorno.")