import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SenderType(str, enum.Enum):
    """Origen del mensaje. Coincide con el ENUM `sender_type_enum` de PostgreSQL."""
    USER = "user"
    BOT = "bot"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    archetype: Mapped[str] = mapped_column(String(50), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)


class UserContact(Base):
    __tablename__ = "user_contacts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    affinity_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # FK compuesta hacia la conversación (user_contacts), igual que en init.sql
        ForeignKeyConstraint(
            ["user_id", "contact_id"],
            ["user_contacts.user_id", "user_contacts.contact_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(
        SAEnum(
            SenderType,
            name="sender_type_enum",
            create_type=False,  # El tipo ya existe (init.sql)
            values_callable=lambda e: [m.value for m in e],  # Persistir 'user'/'bot', no 'USER'/'BOT'
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    used_new_vocabulary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # created_at lo asigna PostgreSQL (NOW()); se recupera tras el commit con refresh()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())