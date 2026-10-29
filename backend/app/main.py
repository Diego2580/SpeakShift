from fastapi import FastAPI

from app.api.routes import auth, chat, contacts, health

app = FastAPI(title="SpeakShift API", version="0.5.0")

# Registro de routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1/contacts")