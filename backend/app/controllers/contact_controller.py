import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Contact, UserContact
from app.schemas.contact import UserContactResponse


def get_user_contacts(db: Session, user_id: uuid.UUID) -> list[UserContactResponse]:
    """
    Devuelve los contactos de un usuario junto con su afinidad y estado de
    desbloqueo, mediante un JOIN entre `contacts` y `user_contacts`.
    Si el usuario no tiene contactos asignados, devuelve una lista vacía.
    """
    stmt = (
        select(Contact, UserContact)
        .join(UserContact, UserContact.contact_id == Contact.id)
        .where(UserContact.user_id == user_id)
        .order_by(Contact.name.asc())  # Orden estable para la lista de la UI
    )
    rows = db.execute(stmt).all()

    # Cada fila es una tupla (Contact, UserContact): se combinan en un solo objeto
    return [
        UserContactResponse(
            id=contact.id,
            name=contact.name,
            archetype=contact.archetype,
            affinity_score=relation.affinity_score,
            is_unlocked=relation.is_unlocked,
        )
        for contact, relation in rows
    ]