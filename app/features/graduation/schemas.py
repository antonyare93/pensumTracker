from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class MissingSubject(_Frozen):
    code: str
    name: str
    credits: int


class MissingBank(_Frozen):
    """Banco de electivas que aún no se cumple. El portal solo lista estos."""

    name: str
    credits_required: int
    credits_approved: int
    credits_missing: int
    # Algunos bancos (p.ej. práctica) se cumplen por número de materias, no por créditos.
    subjects_required: int | None
    subjects_approved: int | None
    subjects_missing: int | None
    options: list[MissingSubject]


class PendingGrade(_Frozen):
    code: str
    name: str
    semester: str


class MissingForGraduation(_Frozen):
    mandatory: list[MissingSubject]
    banks: list[MissingBank]
    pending: list[PendingGrade]
