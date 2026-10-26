-- =============================================================================
-- SpeakShift - Esquema inicial (PostgreSQL 16)
-- Se ejecuta automáticamente al crear el volumen por primera vez.
-- =============================================================================

-- gen_random_uuid() es nativo desde PG13; no requiere extensión.

-- -----------------------------------------------------------------------------
-- Tipos ENUM
-- -----------------------------------------------------------------------------
CREATE TYPE sender_type_enum AS ENUM ('user', 'bot');

-- -----------------------------------------------------------------------------
-- Función + trigger genérico para mantener updated_at
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Tabla: users
-- -----------------------------------------------------------------------------
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username            VARCHAR(50) NOT NULL UNIQUE,
    hidden_level_score  INTEGER NOT NULL DEFAULT 0 CHECK (hidden_level_score >= 0),  -- Nivel oculto de idioma (no visible al usuario)
    streak_days         INTEGER NOT NULL DEFAULT 0 CHECK (streak_days >= 0),         -- Racha de días consecutivos
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Tabla: contacts (personajes IA)
-- -----------------------------------------------------------------------------
CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,
    archetype       VARCHAR(50)  NOT NULL,   -- Ej: 'amigo', 'jefe', 'profesor'
    system_prompt   TEXT NOT NULL,           -- Prompt de sistema que define la personalidad de la IA
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contacts_archetype ON contacts (archetype);

-- -----------------------------------------------------------------------------
-- Tabla pivote: user_contacts (relación N:M con atributos propios)
-- -----------------------------------------------------------------------------
CREATE TABLE user_contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    affinity_score  INTEGER NOT NULL DEFAULT 0,       -- Nivel de afinidad usuario <-> contacto
    is_unlocked     BOOLEAN NOT NULL DEFAULT FALSE,   -- Contacto desbloqueado por progreso
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Un usuario solo puede tener una relación por contacto.
    -- También es requisito para la FK compuesta desde messages.
    CONSTRAINT uq_user_contact UNIQUE (user_id, contact_id)
);

CREATE INDEX idx_user_contacts_contact ON user_contacts (contact_id);

-- -----------------------------------------------------------------------------
-- Tabla: messages
-- -----------------------------------------------------------------------------
CREATE TABLE messages (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    contact_id              UUID NOT NULL,
    sender_type             sender_type_enum NOT NULL,        -- 'user' o 'bot'
    content                 TEXT NOT NULL,
    used_new_vocabulary     BOOLEAN NOT NULL DEFAULT FALSE,   -- ¿El usuario usó vocabulario nuevo en este mensaje?
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- FK compuesta: garantiza que el mensaje pertenezca a una conversación
    -- (user_contacts) existente. Si se elimina la relación, se borran sus mensajes.
    CONSTRAINT fk_messages_user_contact
        FOREIGN KEY (user_id, contact_id)
        REFERENCES user_contacts (user_id, contact_id)
        ON DELETE CASCADE
);

-- Índice clave para cargar el historial de un chat ordenado cronológicamente
CREATE INDEX idx_messages_conversation
    ON messages (user_id, contact_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Triggers de auditoría (updated_at automático)
-- -----------------------------------------------------------------------------
CREATE TRIGGER trg_users_updated_at         BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_contacts_updated_at      BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_contacts_updated_at BEFORE UPDATE ON user_contacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_messages_updated_at      BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();