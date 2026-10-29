from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt como esquema de hash; "auto" marca como obsoletos los hashes de otros esquemas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Devuelve el hash bcrypt (con salt incluido) de la contraseña."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña en claro contra su hash. Nunca lanza excepción."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):  # Hash corrupto o vacío
        return False


# Hash de relleno: permite verificar contra algo cuando el email no existe,
# igualando el tiempo de respuesta y evitando enumerar usuarios por timing.
DUMMY_HASH = get_password_hash("speakshift-dummy-password")


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """
    Crea un JWT firmado. `subject` es el id del usuario (claim estándar "sub",
    que PyJWT exige como string).
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS))
    payload = {"sub": str(subject), "iat": now, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decodifica y valida el JWT (firma + expiración).
    Lanza jwt.PyJWTError si el token es inválido o ha expirado.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])