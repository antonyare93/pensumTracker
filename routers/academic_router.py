import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from models.academic import AcademicRecord
from scraper.portal_scraper import PortalScraper
from services.academic_service import AcademicRecordBuilder

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class SessionRequest(BaseModel):
    cookies: dict[str, str]
    pensum_version: int = 0


class LoginRequest(BaseModel):
    username: str
    password: str
    pensum_version: int = 0


def get_scraper(body: SessionRequest) -> PortalScraper:
    return PortalScraper(cookies=body.cookies, pensum_version=body.pensum_version)


def _ndjson(stage: str, **payload) -> str:
    return json.dumps({"stage": stage, **payload}, ensure_ascii=False) + "\n"


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/session")
def validate_session(body: SessionRequest):
    scraper = get_scraper(body)
    if not scraper.validate_session():
        log.warning("validate_session: sesión inválida o expirada")
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    student_name, program_name, program_code = scraper.fetch_student_info()
    log.info("validate_session: ok | program_code=%s", program_code)
    return {
        "valid": True,
        "student_name": student_name,
        "program_name": program_name,
        "program_code": program_code,
    }


def _resolve_version(scraper: PortalScraper, requested_version: int,
                     program_code: str, version_actual: int, tag: str) -> int:
    if requested_version == 0:
        # Usar la versión asignada al estudiante (no la vigente del programa).
        assigned = scraper.fetch_assigned_pensum_version(program_code)
        scraper._pensum_version = assigned or version_actual
        log.info("%s: versión auto | asignada=%s vigente=%d -> %d",
                 tag, assigned, version_actual, scraper._pensum_version)
    else:
        scraper._pensum_version = requested_version
    log.info("%s: pensum_version efectiva=%d | enrolled=%s",
             tag, scraper._pensum_version, scraper._enrolled_version)
    return scraper._pensum_version


def _iter_stages(
    scraper: PortalScraper,
    requested_version: int,
    tag: str,
) -> Iterator[dict]:
    """Única fuente de verdad del expediente: emite las etapas en orden de
    disponibilidad. El endpoint de streaming las serializa a NDJSON y el
    endpoint clásico se queda con la última ("record")."""
    student_name, program_name, program_code = scraper.fetch_student_info()
    log.info("%s: student_info | program_code=%s has_name=%s", tag, program_code, bool(student_name))
    yield {
        "stage": "student_info",
        "data": {
            "student_name": student_name,
            "program_name": program_name,
            "program_code": program_code,
        },
    }

    version_actual, versiones, catalog_total = scraper.fetch_program_info(program_code)
    log.info("%s: program_info | version_actual=%d versiones=%s catalog_total=%d",
             tag, version_actual, versiones, catalog_total)

    pensum_version = _resolve_version(
        scraper, requested_version, program_code, version_actual, tag)
    enrolled_version = scraper._enrolled_version
    yield {
        "stage": "program_info",
        "data": {
            "pensum_version": pensum_version,
            "version_actual": version_actual,
            "enrolled_version": enrolled_version,
            "versiones": versiones,
            "total_credits": catalog_total,
        },
    }

    # Catálogo del pensum antes de la historia académica: la malla se puede
    # pintar de inmediato mientras se resuelven notas y homologaciones.
    yield {
        "stage": "pensum",
        "data": {"subjects": [s.model_dump() for s in scraper.fetch_pensum_subjects()]},
    }

    subjects = scraper.fetch_curriculum()
    passed   = sum(1 for s in subjects if s.cursada)
    current  = sum(1 for s in subjects if s.cursando)
    log.info("%s: curriculum | total=%d cursadas=%d cursando=%d", tag, len(subjects), passed, current)
    yield {"stage": "pensum", "data": {"subjects": [s.model_dump() for s in subjects]}}

    total_credits, bank_requirements = scraper.resolve_total_credits(catalog_total, subjects)
    if total_credits != catalog_total:
        yield {
            "stage": "program_info",
            "data": {
                "pensum_version": pensum_version,
                "version_actual": version_actual,
                "enrolled_version": enrolled_version,
                "versiones": versiones,
                "total_credits": total_credits,
            },
        }

    record = AcademicRecordBuilder().build(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=pensum_version,
        version_actual=version_actual,
        enrolled_version=enrolled_version,
        versiones=versiones,
        total_credits=total_credits,
        subjects=subjects,
        bank_requirements=bank_requirements,
    )
    log.info(
        "%s: record construido | credits=%d/%d en_curso=%d",
        tag, record.completed_credits, record.total_credits, record.in_progress_credits,
    )
    yield {"stage": "record", "data": record.model_dump()}


def _build_record(scraper: PortalScraper, requested_version: int, tag: str) -> AcademicRecord:
    record = None
    for event in _iter_stages(scraper, requested_version, tag):
        if event["stage"] == "record":
            record = AcademicRecord.model_validate(event["data"])
    if record is None:
        raise HTTPException(status_code=502, detail="No se pudo construir el expediente")
    return record


def _stream_record(
    scraper: PortalScraper,
    requested_version: int,
    tag: str,
) -> Iterator[str]:
    try:
        for event in _iter_stages(scraper, requested_version, tag):
            yield _ndjson(event["stage"], data=event["data"])
    except HTTPException as exc:
        log.warning("%s: error del portal durante el streaming: %s", tag, exc.detail)
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        yield _ndjson("error", status=exc.status_code, detail=detail)
    except Exception:
        log.exception("%s: error inesperado durante el streaming", tag)
        yield _ndjson("error", status=500, detail="Error inesperado al obtener el pensum")


def _login_scraper(body: LoginRequest, tag: str) -> PortalScraper:
    log.info("%s: intento de autenticación | pensum_version=%d", tag, body.pensum_version)
    scraper = PortalScraper(cookies={}, pensum_version=body.pensum_version)
    if not scraper.login(body.username, body.password):
        log.warning("%s: autenticación fallida", tag)
        raise HTTPException(status_code=401, detail="Credenciales inválidas o sesión no establecida")
    log.info("%s: autenticación exitosa", tag)
    return scraper


@router.post("/login")
def login_and_fetch(body: LoginRequest) -> AcademicRecord:
    scraper = _login_scraper(body, "login")
    return _build_record(scraper, body.pensum_version, "login")


@router.post("/login/stream")
def login_and_stream(body: LoginRequest):
    scraper = _login_scraper(body, "login/stream")
    return StreamingResponse(
        _stream_record(scraper, body.pensum_version, "login/stream"),
        media_type="application/x-ndjson",
        headers=_STREAM_HEADERS,
    )


@router.post("/academic-record")
def get_academic_record(body: SessionRequest) -> AcademicRecord:
    log.info("academic-record: inicio | pensum_version=%d", body.pensum_version)
    scraper = get_scraper(body)
    return _build_record(scraper, body.pensum_version, "academic-record")


@router.post("/academic-record/stream")
def stream_academic_record(body: SessionRequest):
    log.info("academic-record/stream: inicio | pensum_version=%d", body.pensum_version)
    scraper = get_scraper(body)
    if not scraper.validate_session():
        log.warning("academic-record/stream: sesión inválida o expirada")
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return StreamingResponse(
        _stream_record(scraper, body.pensum_version, "academic-record/stream"),
        media_type="application/x-ndjson",
        headers=_STREAM_HEADERS,
    )
