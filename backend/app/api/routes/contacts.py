import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers import contact_controller
from app.db.session import get_db
from app.schemas.contact import UserContactResponse

# El prefijo (/api/v1/contacts) se define al registrar el router en main.py
router = APIRouter(tags=["Contacts"])


# `def` síncrona: FastAPI la ejecuta en un threadpool (consulta bloqueante a BD)
@router.get(
    "/",
    response_model=list[UserContactResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista los contactos del usuario y su estado de desbloqueo",
)
def list_user_contacts(
    user_id: uuid.UUID = Query(..., description="ID del usuario"),
    db: Session = Depends(get_db),
):
    return contact_controller.get_user_contacts(db, user_id)