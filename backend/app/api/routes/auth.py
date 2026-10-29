import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import Contact, User, UserContact
from app.schemas.auth import Token, UserCreate, UserResponse

logger = logging.getLogger(__name__)

# El prefijo (/api/v1/auth) se define al registrar el router en main.py
router = APIRouter(tags=["Auth"])

# Contactos que todo usuario nuevo recibe automáticamente: (contact_id, is_unlocked)
EMMA_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
LIAM_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
INITIAL_CONTACTS = (
    (EMMA_ID, True),   # Emma: disponible desde el inicio
    (LIAM_ID, False),  # Liam: se desbloquea con la progresión
)


def _generate_username(email: str) -> str:
    """
    `users.username` es NOT NULL y UNIQUE (VARCHAR 50). Se deriva del email
    y se añade un sufijo aleatorio para garantizar unicidad (máx. 49 caracteres).
    """
    local_part = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0])[:40] or "user"
    return f"{local_part}_{uuid.uuid4().hex[:8]}"


# -----------------------------------------------------------------------------
# POST /register
# -----------------------------------------------------------------------------
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un usuario y le asigna a Emma (desbloqueada) y Liam (bloqueado)",
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    email = str(payload.email).lower()

    # Comprobación temprana para devolver un 409 claro
    if db.execute(select(User.id).where(User.email == email)).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado.")

    user = User(
        username=_generate_username(email),
        email=email,
        hashed_password=get_password_hash(payload.password),
        name=payload.name,
        english_level=payload.english_level,
    )

    try:
        db.add(user)
        db.flush()  # Asigna user.id sin cerrar la transacción

        # Solo se vinculan los contactos que existan en BD (evita romper la FK)
        wanted_ids = [contact_id for contact_id, _ in INITIAL_CONTACTS]
        existing_ids = set(
            db.execute(select(Contact.id).where(Contact.id.in_(wanted_ids))).scalars().all()
        )

        for contact_id, is_unlocked in INITIAL_CONTACTS:
            if contact_id not in existing_ids:
                logger.warning("Contacto inicial %s no existe en BD; no se asigna.", contact_id)
                continue
            db.add(
                UserContact(
                    user_id=user.id,
                    contact_id=contact_id,
                    affinity_score=0,
                    is_unlocked=is_unlocked,
                )
            )

        # Usuario + relaciones en una sola transacción: o se crea todo o nada
        db.commit()
        db.refresh(user)
    except IntegrityError:
        # Carrera: otro request registró el mismo email entre el SELECT y el INSERT
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya está registrado.")
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Error al registrar el usuario.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear el usuario.",
        )

    return user


# -----------------------------------------------------------------------------
# POST /login  (OAuth2: formulario con `username` = email y `password`)
# -----------------------------------------------------------------------------
@router.post(
    "/login",
    response_model=Token,
    summary="Valida email y password y devuelve un JWT",
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # El estándar OAuth2 llama "username" al campo; aquí contiene el email
    email = form_data.username.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # Se verifica SIEMPRE contra algún hash (real o de relleno): mismo tiempo de respuesta
    hashed = user.hashed_password if user is not None and user.hashed_password else DUMMY_HASH
    password_ok = verify_password(form_data.password, hashed)

    if user is None or not user.hashed_password or not password_ok:
        # Mensaje genérico: no revela si el email existe
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, token_type="bearer")