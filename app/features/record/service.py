"""Etapa record del stream: arma el expediente leyendo el portal en orden de disponibilidad."""

import logging
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from app.core.stream import Event, StreamContext
from app.features.record.domain.credits import resolve_total_credits
from app.features.record.domain.grades import PassedSubject, merge_passed, passed_subject
from app.features.record.domain.homologation import homologate
from app.features.record.domain.record import build_record
from app.features.record.schemas import AcademicRecord, EnrolledOutsidePensum, Subject
from app.features.record.sources.gateway import PortalRecordSource, RecordSource
from app.features.record.sources.models import CursumSubject, EnrolledSubject, StudentInfo
from app.portal.session import PortalSession

log = logging.getLogger(__name__)


def _subject(item: CursumSubject, cursada: bool, nota: float | None, cursando: bool) -> Subject:
    return Subject(
        code=item.code,
        name=item.name,
        credits=item.credits,
        semester=item.level,
        obligatoria=item.obligatoria,
        elective_bank=item.elective_bank,
        prerequisites=list(item.prerequisites),
        corequisites=list(item.corequisites),
        cursada=cursada,
        nota=nota,
        cursando=cursando,
    )


def merge_curriculum(
    items: Sequence[CursumSubject],
    passed: Mapping[str, PassedSubject],
    current: Collection[str],
) -> list[Subject]:
    """Materias del pensum con lo aprobado (directo u homologado) y lo matriculado."""
    if not items:
        return []
    homologation = homologate(passed, {item.code: item.name for item in items})
    subjects: list[Subject] = []
    for item in items:
        code = item.code
        cursada = code in passed or code in homologation
        # Una nota textual (None) cede ante la nota homologada, como siempre.
        nota = (passed[code].grade if code in passed else None) or homologation.get(code)
        subjects.append(_subject(item, cursada, nota, code in current))
    return subjects


def enrolled_outside_pensum(
    current: Sequence[EnrolledSubject], items: Sequence[CursumSubject]
) -> list[EnrolledOutsidePensum]:
    """Matriculadas que no están en el pensum: sin esto se perdían sin rastro."""
    in_pensum = {item.code for item in items}
    return [
        EnrolledOutsidePensum(code=s.code, name=s.name) for s in current if s.code not in in_pensum
    ]


@dataclass(frozen=True)
class _Program:
    version_actual: int
    versiones: list[int]
    catalog_total: int
    pensum_version: int
    enrolled_version: int | None

    def info(self, total_credits: int) -> Event:
        return {
            "stage": "program_info",
            "data": {
                "pensum_version": self.pensum_version,
                "version_actual": self.version_actual,
                "enrolled_version": self.enrolled_version,
                "versiones": self.versiones,
                "total_credits": total_credits,
            },
        }


def _pensum_event(subjects: Sequence[Subject]) -> Event:
    return {"stage": "pensum", "data": {"subjects": [s.model_dump() for s in subjects]}}


class RecordStage:
    name = "record"
    optional = False

    def __init__(
        self, source_factory: Callable[[PortalSession], RecordSource] = PortalRecordSource
    ) -> None:
        self._source_factory = source_factory

    def run(self, ctx: StreamContext) -> Iterator[Event]:
        source = self._source_factory(ctx.session)

        student = source.student_info()
        log.info(
            "record: student_info | program_code=%s has_name=%s",
            student.program_code,
            bool(student.student_name),
        )
        yield {"stage": "student_info", "data": student.model_dump()}

        program = _program(source, student.program_code, ctx.requested_version)
        yield program.info(program.catalog_total)

        # Catálogo del pensum antes de la historia académica: la malla se puede
        # pintar de inmediato mientras se resuelven notas y homologaciones.
        items = source.curriculum(student.program_code, program.pensum_version)
        yield _pensum_event(merge_curriculum(items, {}, ()))

        subjects, outside = _curriculum(source, student.program_code, program.pensum_version)
        yield _pensum_event(subjects)

        official = source.official_pensum()
        total_credits, bank_requirements = resolve_total_credits(
            program.catalog_total,
            subjects,
            official.version if official else None,
            official.bank_minimums if official else {},
            program.pensum_version,
        )
        if total_credits != program.catalog_total:
            yield program.info(total_credits)

        record = _record(student, program, total_credits, subjects, bank_requirements, outside)
        ctx.results["record"] = record
        yield {"stage": "record", "data": record.model_dump()}


def _program(source: RecordSource, program_code: str, requested_version: int) -> _Program:
    program = source.program(program_code)
    if program is None:
        version_actual, versiones, catalog_total = 0, [], 0
    else:
        # Cursum puede mandar null en versionActual o creditosGrado y pasa tal cual.
        version_actual = cast(int, program.version_actual)
        versiones = program.versiones
        catalog_total = cast(int, program.total_credits)
    log.info(
        "record: program_info | version_actual=%d versiones=%s catalog_total=%d",
        version_actual,
        versiones,
        catalog_total,
    )
    enrolled_version: int | None = None
    if requested_version == 0:
        # Versión asignada al estudiante, no la vigente del programa.
        assigned, enrolled_version = _assigned_version(source, program_code)
        pensum_version = assigned or version_actual
        log.info(
            "record: versión auto | asignada=%s vigente=%d -> %d",
            assigned,
            version_actual,
            pensum_version,
        )
    else:
        pensum_version = requested_version
    log.info("record: pensum_version efectiva=%d | enrolled=%s", pensum_version, enrolled_version)
    return _Program(version_actual, versiones, catalog_total, pensum_version, enrolled_version)


def _assigned_version(source: RecordSource, program_code: str) -> tuple[int | None, int | None]:
    """Versión asignada y versión matriculada conocida tras resolverla.

    Prioridad: data-version del selector de programas (historia) y, si no hay,
    la versión del pensum oficial (ayudame2), que también queda como matriculada.
    """
    page = source.historia(program_code)
    enrolled = page.enrolled_version if page.selector_applied else None
    if enrolled:
        log.info("record: versión asignada desde historia=%d", enrolled)
        return enrolled, enrolled
    official = source.official_pensum()
    if official is not None and official.version:
        log.info("record: versión asignada desde pensum oficial=%d", official.version)
        return official.version, official.version
    log.warning("record: no se pudo determinar la versión asignada")
    return None, enrolled


def _curriculum(
    source: RecordSource, program_code: str, pensum_version: int
) -> tuple[list[Subject], list[EnrolledOutsidePensum]]:
    passed = _passed(source, program_code)
    enrolled = source.current_subjects()
    current = {s.code for s in enrolled}
    log.info(
        "record: cursando=%d | program_code=%s pensum_version=%d",
        len(current),
        program_code,
        pensum_version,
    )
    items = source.curriculum(program_code, pensum_version)
    subjects = merge_curriculum(items, passed, current)
    outside = enrolled_outside_pensum(enrolled, items)
    log.info(
        "record: curriculum | total=%d cursadas=%d cursando=%d fuera_del_pensum=%d",
        len(subjects),
        sum(1 for s in subjects if s.cursada),
        sum(1 for s in subjects if s.cursando),
        len(outside),
    )
    return subjects, outside


def _passed(source: RecordSource, program_code: str) -> dict[str, PassedSubject]:
    # La historia se vuelve a pedir aquí: el portal no la cachea y el orden de
    # las peticiones decide en qué evento sale un error.
    semester_codes = source.historia(program_code).semester_codes
    log.info("record: %d semestres encontrados", len(semester_codes))
    passed = merge_passed(_passed_in_semester(source, code) for code in semester_codes)
    log.info("record: %d materias aprobadas", len(passed))
    return passed


def _passed_in_semester(source: RecordSource, semester_code: str) -> list[PassedSubject]:
    rows = source.semester_grades(semester_code)
    found = (passed_subject(r.code, r.name, r.raw_grade) for r in rows)
    return [p for p in found if p is not None]


def _record(
    student: StudentInfo,
    program: _Program,
    total_credits: int,
    subjects: list[Subject],
    bank_requirements: dict[str, int],
    outside: list[EnrolledOutsidePensum],
) -> AcademicRecord:
    record = build_record(
        student_name=student.student_name,
        program_name=student.program_name,
        program_code=student.program_code,
        pensum_version=program.pensum_version,
        version_actual=program.version_actual,
        enrolled_version=program.enrolled_version,
        versiones=program.versiones,
        total_credits=total_credits,
        subjects=subjects,
        bank_requirements=bank_requirements,
        enrolled_outside_pensum=outside,
    )
    log.info(
        "record: expediente construido | credits=%d/%d en_curso=%d",
        record.completed_credits,
        record.total_credits,
        record.in_progress_credits,
    )
    return record
