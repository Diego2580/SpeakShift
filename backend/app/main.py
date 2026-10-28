from fastapi import FastAPI

from app.api.routes import chat, health

app = FastAPI(title="SpeakShift API", version="0.2.0")

# Registro de routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")