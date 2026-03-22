from pydantic import BaseModel


class Subject(BaseModel):
    code: str
    name: str
    credits: int
    semester: int | None = None
    obligatoria: bool = True
    elective_bank: str | None = None
    prerequisites: list[str] = []
    corequisites: list[str] = []
    cursada: bool = False
    nota: float | None = None
    cursando: bool = False
    status: str = "locked"


class ElectiveBank(BaseModel):
    name: str
    credits_required: int
    credits_approved: int
    subject_codes: list[str]


class AcademicRecord(BaseModel):
    student_name: str
    program_name: str
    program_code: str
    pensum_version: int
    version_actual: int
    versiones: list[int]
    total_credits: int
    completed_credits: int
    in_progress_credits: int
    subjects: list[Subject]
    elective_banks: list[ElectiveBank] = []
