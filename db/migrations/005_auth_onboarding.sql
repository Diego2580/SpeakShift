-- =============================================================================
-- SpeakShift - Issue #5: Autenticación y onboarding CEFR
-- Idempotente: se puede ejecutar varias veces sin error.
-- =============================================================================

-- Columnas nuevas. email/hashed_password/name admiten NULL para no romper
-- usuarios creados antes de la autenticación (p. ej. el usuario de pruebas).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email            VARCHAR(255),
    ADD COLUMN IF NOT EXISTS hashed_password  VARCHAR(255),
    ADD COLUMN IF NOT EXISTS name             VARCHAR(100),
    ADD COLUMN IF NOT EXISTS english_level    VARCHAR(10) NOT NULL DEFAULT 'A1';

-- Solo se admiten niveles CEFR válidos
ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_english_level;
ALTER TABLE users
    ADD CONSTRAINT chk_users_english_level
    CHECK (english_level IN ('A1', 'A2', 'B1', 'B2', 'C1', 'Native'));

-- Email único e indexado (los NULL no colisionan entre sí en PostgreSQL)
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);