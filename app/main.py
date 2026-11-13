from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import DEFAULT_ORIGINS, Settings, get_settings
from app.core.http_errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.stream import Stage
from app.features.grades.service import GradesStage
from app.features.record.router import build_router
from app.features.record.service import RecordStage


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()

    app = FastAPI(title="Pensum Tracker API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*DEFAULT_ORIGINS, *settings.allowed_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    # Las etapas de módulos nuevos se agregan a esta lista.
    stages: list[Stage] = [RecordStage(), GradesStage()]
    app.include_router(build_router(stages))
    return app


app = create_app()
