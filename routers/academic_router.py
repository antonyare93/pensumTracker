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
    student_name, program_name, program_code, _ = scraper.fetch_student_info()
    log.info("validate_session: ok | program_code=%s", program_code)
    return {
        "valid": True,
        "student_name": student_name,
        "program_name": program_name,
        "program_code": program_code,
    }


@router.post("/login")
def login_and_fetch(body: LoginRequest) -> AcademicRecord:
    log.info("login: intento de autenticación | pensum_version=%d", body.pensum_version)
    scraper = PortalScraper(cookies={}, pensum_version=body.pensum_version)

    if not scraper.login(body.username, body.password):
        log.warning("login: autenticación fallida")
        raise HTTPException(status_code=401, detail="Credenciales inválidas o sesión no establecida")

    log.info("login: autenticación exitosa")

    student_name, program_name, program_code = scraper.fetch_student_info()
    log.info("login: student_info | program_code=%s has_name=%s", program_code, bool(student_name))

    version_actual, versiones, total_credits = scraper.fetch_program_info(program_code)
    log.info("login: program_info | version_actual=%d versiones=%s total_credits=%d",
             version_actual, versiones, total_credits)

    if body.pensum_version == 0:
        scraper._pensum_version = version_actual
    log.info("login: pensum_version efectiva=%d", scraper._pensum_version)

    subjects = scraper.fetch_curriculum()
    passed   = sum(1 for s in subjects if s.cursada)
    current  = sum(1 for s in subjects if s.cursando)
    log.info("login: curriculum | total=%d cursadas=%d cursando=%d", len(subjects), passed, current)

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
        "login: record construido | credits=%d/%d en_curso=%d",
        record.completed_credits, record.total_credits, record.in_progress_credits,
    )
    return record


@router.post("/academic-record")
def get_academic_record(body: SessionRequest) -> AcademicRecord:
    log.info("academic-record: inicio | pensum_version=%d", body.pensum_version)
    scraper = get_scraper(body)

    student_name, program_name, program_code = scraper.fetch_student_info()
    log.info("academic-record: student_info | program_code=%s has_name=%s", program_code, bool(student_name))

    version_actual, versiones, total_credits = scraper.fetch_program_info(program_code)
    log.info("academic-record: program_info | version_actual=%d versiones=%s total_credits=%d",
             version_actual, versiones, total_credits)

    if body.pensum_version == 0:
        scraper._pensum_version = version_actual
    log.info("academic-record: pensum_version efectiva=%d", scraper._pensum_version)

    subjects = scraper.fetch_curriculum()
    passed   = sum(1 for s in subjects if s.cursada)
    current  = sum(1 for s in subjects if s.cursando)
    log.info("academic-record: curriculum | total=%d cursadas=%d cursando=%d", len(subjects), passed, current)

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
        "academic-record: record construido | credits=%d/%d en_curso=%d",
        record.completed_credits, record.total_credits, record.in_progress_credits,
    )
    return record
