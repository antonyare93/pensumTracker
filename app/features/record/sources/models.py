from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class StudentInfo(_Frozen):
    student_name: str
    program_name: str
    program_code: str


class EnrolledSubject(_Frozen):
    """Materia de "MATERIAS MATRICULADAS" en la constancia. El nombre puede faltar."""

    code: str
    name: str | None


class ProgramOption(_Frozen):
    """Opción del selector de programas y el formulario que hay que enviar."""

    code: str
    version: int | None
    form_data: dict[str, str]


class HistoriaPage(_Frozen):
    """Historia académica ya resuelta: semestres y la versión del selector, si se aplicó."""

    semester_codes: list[str]
    selector_applied: bool
    enrolled_version: int | None


class GradeRow(_Frozen):
    """Fila de un semestre, sin interpretar la nota."""

    code: str
    name: str
    raw_grade: str


class OfficialPensum(_Frozen):
    version: int | None
    bank_minimums: dict[str, int]


class CursumProgram(_Frozen):
    code: str
    version_actual: int | None
    versiones: list[int]
    total_credits: int | None


class CursumSubject(_Frozen):
    code: str
    name: str
    credits: int
    level: int | None
    obligatoria: bool
    elective_bank: str | None
    prerequisites: list[str]
    corequisites: list[str]
