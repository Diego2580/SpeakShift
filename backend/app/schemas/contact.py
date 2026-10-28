import uuid

from pydantic import BaseModel, ConfigDict


class ContactOut(BaseModel):
    """Datos públicos de un personaje (contacto) de la IA."""

    # Permite construir el schema directamente desde objetos ORM
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    archetype: str


class UserContactResponse(ContactOut):
    """
    Contacto + estado de la relación con un usuario concreto.
    Hereda id, name y archetype de ContactOut (estructura plana, ideal para la UI).
    """

    affinity_score: int
    is_unlocked: bool