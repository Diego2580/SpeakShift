import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.entities import User

# tokenUrl habilita el botón "Authorize" de Swagger (/docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decodifica el JWT y devuelve el `User` de la BD; 401 si algo no cuadra."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = uuid.UUID(subject)
    except (jwt.PyJWTError, ValueError) as exc:  # Token inválido/expirado o "sub" no UUID
        raise credentials_exception from exc

    user = db.get(User, user_id)
    if user is None:  # Token válido pero el usuario ya no existe
        raise credentials_exception
    return user