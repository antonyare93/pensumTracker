from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Evaluation(_Frozen):
    """Evaluación que programó el docente. Sin nota si aún no la sube o falta la encuesta."""

    name: str
    percent: float
    grade: float | None


class CourseGrades(_Frozen):
    code: str
    name: str
    evaluations: list[Evaluation]
    # El portal oculta las notas hasta que el estudiante evalúa a un docente.
    survey_pending: bool
