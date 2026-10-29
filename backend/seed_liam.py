"""
Seeder: inserta el contacto "Liam" (Tech Recruiter) y su relación con el usuario de prueba.
Es idempotente: se puede ejecutar varias veces sin duplicar datos ni borrar progreso.

Uso (dentro del contenedor):
    docker compose cp backend/seed_liam.py api:/code/seed_liam.py
    docker compose exec api python seed_liam.py
"""
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.entities import Contact, User, UserContact

LIAM_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

LIAM_NAME = "Liam"
LIAM_ARCHETYPE = "Tech Recruiter"
LIAM_SYSTEM_PROMPT = (
    "You are Liam, a senior tech recruiter. "
    "You conduct technical interviews in English. "
    "Keep your answers short."
)


def seed() -> None:
    with SessionLocal() as db:
        try:
            # La FK de user_contacts exige que el usuario exista
            if db.get(User, USER_ID) is None:
                print(f"[ERROR] El usuario {USER_ID} no existe en la tabla 'users'. Créalo primero.")
                sys.exit(1)

            # --- Contacto: se crea o se actualiza -----------------------------
            contact = db.get(Contact, LIAM_ID)
            if contact is None:
                db.add(
                    Contact(
                        id=LIAM_ID,
                        name=LIAM_NAME,
                        archetype=LIAM_ARCHETYPE,
                        system_prompt=LIAM_SYSTEM_PROMPT,
                    )
                )
                print(f"[OK] Contacto '{LIAM_NAME}' creado.")
            else:
                contact.name = LIAM_NAME
                contact.archetype = LIAM_ARCHETYPE
                contact.system_prompt = LIAM_SYSTEM_PROMPT
                print(f"[OK] Contacto '{LIAM_NAME}' ya existía: datos actualizados.")

            # --- Relación usuario-contacto: solo se crea si falta -------------
            # (si ya existe NO se toca, para conservar el progreso del usuario)
            relation = db.execute(
                select(UserContact).where(
                    UserContact.user_id == USER_ID,
                    UserContact.contact_id == LIAM_ID,
                )
            ).scalar_one_or_none()

            if relation is None:
                db.add(
                    UserContact(
                        user_id=USER_ID,
                        contact_id=LIAM_ID,
                        affinity_score=0,
                        is_unlocked=False,
                    )
                )
                print("[OK] Relación usuario-contacto creada (affinity_score=0, is_unlocked=False).")
            else:
                print("[OK] La relación ya existía: no se modifica.")

            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            print(f"[ERROR] No se pudo completar el seed: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    seed()