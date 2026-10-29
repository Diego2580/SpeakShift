import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.controllers import chat_controller
from app.db.session import get_db
from app.models.entities import User
from app.schemas.chat import ChatMessageOut, ChatSendRequest

router = APIRouter(prefix="/chat", tags=["Chat"])


# Se define como `def` (síncrona): FastAPI la ejecuta en un threadpool,
# así la llamada bloqueante a la BD y al LLM no congela el event loop.
@router.post(
    "/send",
    response_model=ChatMessageOut,
    status_code=status.HTTP_200_OK,
    summary="Envía un mensaje al contacto y devuelve la respuesta de la IA",
)
def send_chat_message(
    payload: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_controller.send_message(db, current_user.id, payload)


# Ruta final: GET /api/v1/chat/history/{contact_id}?limit=50
@router.get(
    "/history/{contact_id}",
    response_model=list[ChatMessageOut],
    status_code=status.HTTP_200_OK,
    summary="Historial de mensajes con un contacto (del más antiguo al más reciente)",
)
def get_chat_history(
    contact_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200, description="Máximo de mensajes a devolver"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_controller.get_chat_history(db, current_user.id, contact_id, limit)