import json
import logging
import re
import uuid
from functools import lru_cache

from fastapi import HTTPException, status
from openai import OpenAI, OpenAIError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Contact, Message, SenderType, User, UserContact
from app.schemas.chat import ChatSendRequest

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Constantes del Core Loop
# -----------------------------------------------------------------------------
# Mensajes de contexto enviados al LLM (incluye el mensaje actual del usuario)
HISTORY_LIMIT = 6

# Gamificación
BASE_POINTS = 10          # Puntos por cada mensaje enviado
NEW_VOCAB_BONUS = 15      # Puntos extra si el usuario usó vocabulario nuevo
UNLOCK_THRESHOLD = 100    # Afinidad necesaria para desbloquear otro contacto

# Mapa de progresión CEFR: nivel actual -> nivel objetivo
LEVEL_PROGRESSION = {
    "A1": "A2",
    "A2": "B1",
    "B1": "B2",
    "B2": "C1",
    "C1": "Native",
}
DEFAULT_ENGLISH_LEVEL = "A1"

# Mapeo de nuestro sender_type al "role" que espera la API de chat completions
_ROLE_BY_SENDER = {
    SenderType.USER: "user",
    SenderType.BOT: "assistant",
}

# Instrucción que obliga al LLM a responder SOLO en JSON
JSON_INSTRUCTION = (
    "\n\nYou MUST respond ONLY in valid JSON format with this structure: "
    '{"reply": "your message to the user", "used_new_vocab": true/false, '
    '"feedback": "brief internal note"}. '
    'Rules: "reply" is what you say to the user, always staying in character. '
    '"used_new_vocab" must be true only if the user\'s LAST message used new, varied '
    "or advanced vocabulary worth rewarding; otherwise false. "
    '"feedback" is a brief internal note about the user\'s language (never shown to the user). '
    "Do not use markdown, code fences or any text outside the JSON object."
)

# Elimina ```json ... ``` (o ``` ... ```) que algunos modelos añaden alrededor del JSON
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Lógica CEFR: construcción del system prompt
# -----------------------------------------------------------------------------
def _build_system_prompt(contact_prompt: str, english_level: str | None) -> str:
    """
    Concatena al system_prompt del contacto la instrucción de tutor progresivo
    según el nivel CEFR del usuario (nivel actual -> nivel objetivo).
    """
    current_level = english_level if english_level else DEFAULT_ENGLISH_LEVEL
    target_level = LEVEL_PROGRESSION.get(current_level)

    if target_level is None:
        # Nivel "Native" (o desconocido): no hay un nivel superior al que transicionar
        instruction = (
            f"The user's English level is {current_level}. "
            f"Converse naturally using {current_level}-level vocabulary and idiomatic expressions."
        )
    else:
        instruction = (
            f"The user's English level is {current_level}. "
            f"Act as a progressive tutor: converse naturally using {current_level} vocabulary, "
            f"but gently introduce topics and vocabulary from the {target_level} level "
            "to help them transition."
        )

    return f"{contact_prompt}\n\n{instruction}"


# -----------------------------------------------------------------------------
# Cliente LLM (OpenRouter vía SDK oficial de OpenAI)
# -----------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_llm_client() -> OpenAI:
    """Crea (una sola vez) el cliente OpenAI apuntando a OpenRouter."""
    if not settings.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY no está configurada.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de IA no está configurado.",
        )
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=30.0,
        max_retries=1,
        # Cabecera opcional recomendada por OpenRouter (atribución)
        default_headers={"X-Title": "SpeakShift"},
    )


def _candidate_models() -> list[str]:
    """
    Lista ordenada de modelos a intentar: primero LLM_MODEL y luego los de respaldo.
    Los respaldos son opcionales: LLM_FALLBACK_MODELS=modelo-a,modelo-b (CSV o lista).
    """
    models = [settings.LLM_MODEL]
    extra = getattr(settings, "LLM_FALLBACK_MODELS", None)
    if isinstance(extra, str):
        extra = [m.strip() for m in extra.split(",") if m.strip()]
    for model in extra or []:
        if model not in models:
            models.append(model)
    return models


# -----------------------------------------------------------------------------
# Parseo de la respuesta JSON del LLM
# -----------------------------------------------------------------------------
def _to_bool(value) -> bool:
    """Convierte true/"true"/1 a bool de forma tolerante."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _parse_llm_response(raw: str) -> dict:
    """
    Limpia la respuesta (quita fences de Markdown) y la parsea con json.loads.
    Devuelve SIEMPRE un dict: {"reply": str, "used_new_vocab": bool, "feedback": str}.
    Si el JSON es inválido, asume texto plano y devuelve un JSON por defecto.
    """
    text = _FENCE_RE.sub("", raw.strip()).strip()

    # 1er intento: texto limpio. 2º intento: el fragmento entre la primera "{" y la última "}"
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if not isinstance(data, dict):
                raise ValueError("El JSON no es un objeto.")
            reply = data.get("reply")
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("Falta el campo 'reply'.")
            return {
                "reply": reply.strip(),
                "used_new_vocab": _to_bool(data.get("used_new_vocab", False)),
                "feedback": str(data.get("feedback", "")).strip(),
            }
        except (ValueError, TypeError):  # JSONDecodeError hereda de ValueError
            continue

    logger.warning("El LLM no devolvió JSON válido; se usa texto plano. Raw: %r", raw[:200])
    return {
        "reply": raw.strip(),
        "used_new_vocab": False,
        "feedback": "Plain-text response (invalid JSON from model).",
    }


def _generate_bot_reply(system_prompt: str, history: list[Message], user_content: str) -> dict:
    """
    Llama al LLM con system prompt (+ instrucción JSON) + historial + mensaje actual.
    Prueba los modelos en orden (fallback) y devuelve un dict con
    `reply`, `used_new_vocab` y `feedback`.
    """
    messages = [{"role": "system", "content": system_prompt + JSON_INSTRUCTION}]
    for m in history:
        if m.sender_type == SenderType.BOT:
            # Los turnos previos del bot se reenvían con el mismo formato JSON
            # para que el modelo no "aprenda" a responder en texto plano.
            content = json.dumps(
                {"reply": m.content, "used_new_vocab": False, "feedback": ""},
                ensure_ascii=False,
            )
        else:
            content = m.content
        messages.append({"role": _ROLE_BY_SENDER[m.sender_type], "content": content})
    # Mensaje actual del usuario (todavía no persistido)
    messages.append({"role": "user", "content": user_content})

    client = get_llm_client()  # Lanza 503 si falta la API key

    # --- Fallback de modelos: se intenta cada uno hasta obtener una respuesta ---
    for model in _candidate_models():
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=500,
            )
        except OpenAIError as exc:
            logger.warning("El modelo '%s' falló (%s). Probando el siguiente...", model, exc)
            continue

        # OpenRouter puede devolver 200 con `choices` vacío/None ante errores del upstream
        if not completion.choices or not completion.choices[0].message.content:
            logger.warning("El modelo '%s' devolvió una respuesta vacía. Probando el siguiente...", model)
            continue

        logger.info("Respuesta generada con el modelo '%s'.", model)
        return _parse_llm_response(completion.choices[0].message.content)

    logger.error("Todos los modelos fallaron: %s", _candidate_models())
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="El proveedor de IA no respondió correctamente.",
    )


# -----------------------------------------------------------------------------
# Persistencia
# -----------------------------------------------------------------------------
def _save_message(
    db: Session,
    user_id: uuid.UUID,
    contact_id: uuid.UUID,
    sender_type: SenderType,
    content: str,
    used_new_vocabulary: bool = False,
) -> Message:
    """
    Inserta un mensaje, hace commit y devuelve el objeto con sus valores de BD.
    OJO: el commit también confirma cualquier cambio pendiente en la sesión
    (p. ej. los puntos de afinidad); si falla, se hace rollback de todo junto.
    """
    message = Message(
        user_id=user_id,
        contact_id=contact_id,
        sender_type=sender_type,
        content=content,
        used_new_vocabulary=used_new_vocabulary,
    )
    try:
        db.add(message)
        db.commit()
        db.refresh(message)  # Carga created_at generado por PostgreSQL
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Error al guardar el mensaje en la base de datos.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar el mensaje.",
        )
    return message


def _get_recent_history(
    db: Session,
    user_id: uuid.UUID,
    contact_id: uuid.UUID,
    limit: int = HISTORY_LIMIT,
) -> list[Message]:
    """Últimos `limit` mensajes de la conversación, en orden cronológico."""
    stmt = (
        select(Message)
        .where(Message.user_id == user_id, Message.contact_id == contact_id)
        .order_by(Message.created_at.desc())  # Los más recientes primero...
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return list(reversed(rows))  # ...y se invierten a orden cronológico (viejo -> nuevo)


# -----------------------------------------------------------------------------
# Gamificación: puntos y desbloqueo
# -----------------------------------------------------------------------------
def _apply_progression(
    db: Session,
    user_id: uuid.UUID,
    contact_id: uuid.UUID,
    used_new_vocab: bool,
) -> None:
    """
    Suma puntos de afinidad y, si se alcanza el umbral, desbloquea un contacto.

    NO hace commit: los cambios se confirman junto con el mensaje del bot en
    `_save_message`, de modo que puntos y mensaje son atómicos.

    Concurrencia: SELECT ... FOR UPDATE bloquea la fila hasta el commit, así dos
    requests simultáneos del mismo chat no pierden puntos (evita lost updates).
    El bloqueo se toma DESPUÉS de la llamada al LLM para no retener la fila
    durante varios segundos de latencia.
    """
    points = BASE_POINTS + (NEW_VOCAB_BONUS if used_new_vocab else 0)

    try:
        # populate_existing fuerza a leer el valor real de la BD (no el de la identity map)
        relation = db.execute(
            select(UserContact)
            .where(UserContact.user_id == user_id, UserContact.contact_id == contact_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()

        relation.affinity_score += points

        # Mientras la afinidad sea >= umbral, cada mensaje desbloquea un contacto más
        if relation.affinity_score >= UNLOCK_THRESHOLD:
            locked_relation = db.execute(
                select(UserContact)
                .where(UserContact.user_id == user_id, UserContact.is_unlocked.is_(False))
                .order_by(UserContact.contact_id)  # Orden determinista
                .limit(1)
                .with_for_update()
            ).scalar_one_or_none()

            if locked_relation is not None:
                locked_relation.is_unlocked = True
                logger.info(
                    "Usuario %s desbloqueó el contacto %s (afinidad=%s).",
                    user_id,
                    locked_relation.contact_id,
                    relation.affinity_score,
                )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Error al actualizar la progresión del usuario.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar el progreso del usuario.",
        )


# -----------------------------------------------------------------------------
# Caso de uso principal
# -----------------------------------------------------------------------------
def send_message(db: Session, user_id: uuid.UUID, payload: ChatSendRequest) -> Message:
    """
    Flujo completo de POST /chat/send (Core Loop). `user_id` proviene del token JWT.
      1. Valida que exista la conversación (user_contacts) y esté desbloqueada.
      2. Arma el system_prompt (contacto + instrucción CEFR según english_level del usuario),
         recupera el historial previo y llama al LLM (respuesta JSON).
      3. Guarda el mensaje del usuario con `used_new_vocabulary` evaluado por el LLM.
      4. Suma puntos (+10 base, +15 si hubo vocabulario nuevo) y aplica desbloqueos.
      5. Guarda la respuesta del bot (mismo commit que los puntos) y la devuelve.
    """
    contact_id = payload.contact_id

    # Nivel CEFR del usuario, leído desde la BD
    user = db.get(User, user_id)
    if user is None:  # Defensivo: get_current_user ya valida que exista
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    english_level = user.english_level

    # 1. La FK compuesta de `messages` exige que la relación usuario-contacto exista.
    relation = db.execute(
        select(UserContact).where(
            UserContact.user_id == user_id,
            UserContact.contact_id == contact_id,
        )
    ).scalar_one_or_none()

    if relation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La conversación entre este usuario y contacto no existe.",
        )
    if not relation.is_unlocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este contacto aún no está desbloqueado.",
        )

    contact = db.get(Contact, contact_id)
    if contact is None:  # Defensivo: la FK debería impedirlo
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado.")

    # System prompt del contacto + instrucción dinámica CEFR.
    # Se calcula en una variable local: tras cada commit los objetos ORM expiran.
    system_prompt = _build_system_prompt(contact.system_prompt, english_level)

    # 2. Contexto: (HISTORY_LIMIT - 1) mensajes previos + el mensaje actual = HISTORY_LIMIT
    history = _get_recent_history(db, user_id, contact_id, HISTORY_LIMIT - 1)

    try:
        reply_data = _generate_bot_reply(system_prompt, history, payload.content)
    except HTTPException:
        # Si el LLM falla, el mensaje del usuario no se pierde (se guarda sin bonus).
        _save_message(db, user_id, contact_id, SenderType.USER, payload.content)
        raise

    used_new_vocab = reply_data["used_new_vocab"]
    logger.info("Feedback interno del LLM: %s", reply_data["feedback"])

    # 3. Mensaje del usuario, marcado según la evaluación del LLM
    _save_message(
        db,
        user_id,
        contact_id,
        SenderType.USER,
        payload.content,
        used_new_vocabulary=used_new_vocab,
    )

    # 4. Puntos y desbloqueo (se confirman en el commit del paso 5)
    _apply_progression(db, user_id, contact_id, used_new_vocab)

    # 5. Mensaje del bot (commit atómico con los puntos) y respuesta al cliente
    return _save_message(db, user_id, contact_id, SenderType.BOT, reply_data["reply"])


# -----------------------------------------------------------------------------
# Lectura de historial (Issue #3)
# -----------------------------------------------------------------------------
def get_chat_history(
    db: Session,
    user_id: uuid.UUID,
    contact_id: uuid.UUID,
    limit: int = 50,
) -> list[Message]:
    """
    Devuelve los últimos `limit` mensajes de la conversación (user_id + contact_id)
    ordenados por `created_at` ASCENDENTE (del más antiguo al más reciente).

    Se seleccionan primero los más recientes (DESC + LIMIT) y luego se invierte la
    lista; así, con conversaciones largas, la UI recibe el tramo final del chat
    en orden cronológico y no los mensajes más viejos.
    """
    stmt = (
        select(Message)
        .where(Message.user_id == user_id, Message.contact_id == contact_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return list(reversed(rows))