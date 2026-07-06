import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models.academic import AcademicRecord
from scraper.portal_scraper import PortalScraper
from services.academic_service import AcademicRecordBuilder

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class SessionRequest(BaseModel):
    cookies: dict[str, str]
    pensum_version: int = 0


class LoginRequest(BaseModel):
    username: str
    password: str
    pensum_version: int = 0


def get_scraper(body: SessionRequest) -> PortalScraper:
    return PortalScraper(cookies=body.cookies, pensum_version=body.pensum_version)


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


def _build_record(scraper: PortalScraper, requested_version: int, tag: str) -> AcademicRecord:
    student_name, program_name, program_code = scraper.fetch_student_info()
    log.info("%s: student_info | program_code=%s has_name=%s", tag, program_code, bool(student_name))

    version_actual, versiones, total_credits = scraper.fetch_program_info(program_code)
    log.info("%s: program_info | version_actual=%d versiones=%s total_credits=%d",
             tag, version_actual, versiones, total_credits)

    if requested_version == 0:
        # Por defecto usar la versión en la que el estudiante está matriculado;
        # si no se puede determinar, caer a la versión vigente del programa.
        enrolled = scraper.fetch_enrolled_version(program_code)
        scraper._pensum_version = enrolled or version_actual
        log.info("%s: versión auto | matriculada=%s vigente=%d -> %d",
                 tag, enrolled, version_actual, scraper._pensum_version)
    log.info("%s: pensum_version efectiva=%d", tag, scraper._pensum_version)

    subjects = scraper.fetch_curriculum()
    passed   = sum(1 for s in subjects if s.cursada)
    current  = sum(1 for s in subjects if s.cursando)
    log.info("%s: curriculum | total=%d cursadas=%d cursando=%d", tag, len(subjects), passed, current)

    record = AcademicRecordBuilder().build(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=scraper._pensum_version,
        version_actual=version_actual,
        versiones=versiones,
        total_credits=total_credits,
        subjects=subjects,
    )
    log.info(
        "%s: record construido | credits=%d/%d en_curso=%d",
        tag, record.completed_credits, record.total_credits, record.in_progress_credits,
    )
    return record


@router.post("/login")
def login_and_fetch(body: LoginRequest) -> AcademicRecord:
    log.info("login: intento de autenticación | pensum_version=%d", body.pensum_version)
    scraper = PortalScraper(cookies={}, pensum_version=body.pensum_version)

    if not scraper.login(body.username, body.password):
        log.warning("login: autenticación fallida")
        raise HTTPException(status_code=401, detail="Credenciales inválidas o sesión no establecida")

    log.info("login: autenticación exitosa")
    return _build_record(scraper, body.pensum_version, "login")


@router.post("/academic-record")
def get_academic_record(body: SessionRequest) -> AcademicRecord:
    log.info("academic-record: inicio | pensum_version=%d", body.pensum_version)
    scraper = get_scraper(body)
    return _build_record(scraper, body.pensum_version, "academic-record")
