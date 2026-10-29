import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# Niveles CEFR admitidos en el onboarding
EnglishLevel = Literal["A1", "A2", "B1", "B2", "C1", "Native"]


class UserCreate(BaseModel):
    """Payload de POST /auth/register."""

    # Elimina espacios al inicio/final antes de validar
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72, description="Mínimo 8 caracteres")
    name: str = Field(..., min_length=1, max_length=100)
    english_level: EnglishLevel

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt solo procesa los primeros 72 BYTES (los caracteres no ASCII ocupan más)
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar los 72 bytes.")
        return value


class UserResponse(BaseModel):
    """Usuario devuelto al cliente (nunca incluye la contraseña)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None = None
    name: str | None = None
    english_level: str


class Token(BaseModel):
    """Respuesta de POST /auth/login."""

    access_token: str
    token_type: str = "bearer"