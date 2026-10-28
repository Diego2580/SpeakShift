from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers import chat_controller
from app.db.session import get_db
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
def send_chat_message(payload: ChatSendRequest, db: Session = Depends(get_db)):
    return chat_controller.send_message(db, payload)