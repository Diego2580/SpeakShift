import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import SenderType


class ChatSendRequest(BaseModel):
    """Payload de entrada de POST /chat/send."""

    # Elimina espacios al inicio/final ANTES de validar la longitud,
    # así un mensaje de solo espacios se rechaza (422).
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: uuid.UUID
    contact_id: uuid.UUID
    content: str = Field(..., min_length=1, max_length=2000, description="Mensaje del usuario")


class ChatMessageOut(BaseModel):
    """Mensaje generado por el bot, devuelto al cliente."""

    # Permite construir el schema directamente desde el objeto ORM
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    contact_id: uuid.UUID
    sender_type: SenderType
    content: str
    created_at: datetime