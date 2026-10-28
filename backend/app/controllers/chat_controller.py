import logging
import uuid
from functools import lru_cache

from fastapi import HTTPException, status
from openai import OpenAI, OpenAIError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Contact, Message, SenderType, UserContact
from app.schemas.chat import ChatSendRequest

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 6

_ROLE_BY_SENDER = {
    SenderType.USER: "user",
    SenderType.BOT: "assistant",
}

# Lista de modelos gratuitos de respaldo ordenados por prioridad
FALLBACK_MODELS = [
    settings.LLM_MODEL,
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "huggingfaceh4/zephyr-7b-beta:free",
    "microsoft/phi-3-mini-128k-instruct:free"
]

@lru_cache(maxsize=1)
def get_llm_client() -> OpenAI:
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA no está configurado.",
        )
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=30.0,
        max_retries=1,
        default_headers={"X-Title": "SpeakShift"},
    )

def _generate_bot_reply(system_prompt: str, history: list[Message]) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": _ROLE_BY_SENDER[m.sender_type], "content": m.content} for m in history]

    client = get_llm_client()
    
    # Motor de Fallback: Intenta cada modelo hasta que uno funcione
    for model in FALLBACK_MODELS:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=500,
            )
            if completion.choices and completion.choices[0].message.content:
                logger.info(f"Respuesta exitosa usando el modelo: {model}")
                return completion.choices[0].message.content.strip()
        except OpenAIError as exc:
            logger.warning(f"El modelo {model} falló o no está disponible: {exc}")
            continue # Pasa al siguiente modelo en la lista

    logger.error("Todos los modelos de respaldo fallaron.")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Ningún proveedor de IA gratuito está disponible en este momento.",
    )

def _save_message(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID, sender_type: SenderType, content: str) -> Message:
    message = Message(user_id=user_id, contact_id=contact_id, sender_type=sender_type, content=content)
    try:
        db.add(message)
        db.commit()
        db.refresh(message)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar el mensaje.")
    return message

def _get_recent_history(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID) -> list[Message]:
    stmt = select(Message).where(Message.user_id == user_id, Message.contact_id == contact_id).order_by(Message.created_at.desc()).limit(HISTORY_LIMIT)
    rows = db.execute(stmt).scalars().all()
    return list(reversed(rows))

def send_message(db: Session, payload: ChatSendRequest) -> Message:
    relation = db.execute(
        select(UserContact).where(UserContact.user_id == payload.user_id, UserContact.contact_id == payload.contact_id)
    ).scalar_one_or_none()

    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La conversación no existe.")
    if not relation.is_unlocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contacto no desbloqueado.")

    contact = db.get(Contact, payload.contact_id)
    _save_message(db, payload.user_id, payload.contact_id, SenderType.USER, payload.content)
    history = _get_recent_history(db, payload.user_id, payload.contact_id)
    bot_text = _generate_bot_reply(contact.system_prompt, history)
    return _save_message(db, payload.user_id, payload.contact_id, SenderType.BOT, bot_text)

def get_chat_history(db: Session, user_id: uuid.UUID, contact_id: uuid.UUID, limit: int = 50) -> list[Message]:
    """Devuelve el historial de mensajes ordenados cronológicamente."""
    stmt = (
        select(Message)
        .where(Message.user_id == user_id, Message.contact_id == contact_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return list(reversed(rows))