from fastapi import FastAPI

from app.api.routes import health

app = FastAPI(title="SpeakShift API", version="0.1.0")

# Registro de routers
app.include_router(health.router, prefix="/api/v1")