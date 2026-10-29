import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.controllers import chat_controller
from app.db.session import get_db
from app.schemas.chat import ChatMessageOut, ChatSendRequest

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post(
    "/send",
    response_model=ChatMessageOut,
    status_code=status.HTTP_200_OK,
    summary="Envía un mensaje al contacto y devuelve la respuesta de la IA",
)
def send_chat_message(payload: ChatSendRequest, db: Session = Depends(get_db)):
    return chat_controller.send_message(db, payload)


@router.get(
    "/history/{contact_id}",
    response_model=list[ChatMessageOut],
    status_code=status.HTTP_200_OK,
    summary="Historial de mensajes con un contacto (del más antiguo al más reciente)",
)
def get_chat_history(
    contact_id: uuid.UUID,
    user_id: uuid.UUID = Query(..., description="ID del usuario"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de mensajes a devolver"),
    db: Session = Depends(get_db),
):
    return chat_controller.get_chat_history(db, user_id, contact_id, limit)