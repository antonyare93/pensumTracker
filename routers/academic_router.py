from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models.academic import AcademicRecord
from scraper.portal_scraper import PortalScraper
from services.academic_service import AcademicRecordBuilder

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
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    student_name, program_name, program_code = scraper.fetch_student_info()
    return {
        "valid": True,
        "student_name": student_name,
        "program_name": program_name,
        "program_code": program_code,
    }


@router.post("/login")
def login_and_fetch(body: LoginRequest) -> AcademicRecord:
    scraper = PortalScraper(cookies={}, pensum_version=body.pensum_version)
    if not scraper.login(body.username, body.password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas o sesión no establecida")
    student_name, program_name, program_code = scraper.fetch_student_info()
    version_actual, versiones = scraper.fetch_program_info(program_code)
    if body.pensum_version == 0:
        scraper._pensum_version = version_actual
    subjects       = scraper.fetch_curriculum()
    elective_banks = scraper.fetch_elective_banks()
    return AcademicRecordBuilder().build(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=scraper._pensum_version,
        version_actual=version_actual,
        versiones=versiones,
        subjects=subjects,
        elective_banks=elective_banks,
    )


@router.post("/academic-record")
def get_academic_record(body: SessionRequest) -> AcademicRecord:
    scraper = get_scraper(body)
    student_name, program_name, program_code = scraper.fetch_student_info()
    version_actual, versiones = scraper.fetch_program_info(program_code)
    if body.pensum_version == 0:
        scraper._pensum_version = version_actual
    subjects       = scraper.fetch_curriculum()
    elective_banks = scraper.fetch_elective_banks()
    return AcademicRecordBuilder().build(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=scraper._pensum_version,
        version_actual=version_actual,
        versiones=versiones,
        subjects=subjects,
        elective_banks=elective_banks,
    )
