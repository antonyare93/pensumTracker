"""Armado del expediente: progreso, estados de las materias y bancos de electivas."""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from app.features.record.schemas import (
    AcademicRecord,
    ElectiveBank,
    EnrolledOutsidePensum,
    Subject,
)


def bank_progress(subjects: Sequence[Subject]) -> dict[str, int]:
    """Créditos de electivas cursadas o en curso, por banco."""
    progress: dict[str, int] = defaultdict(int)
    for s in subjects:
        if s.obligatoria:
            continue
        if (s.cursada or s.cursando) and s.elective_bank:
            progress[s.elective_bank] += s.credits
    return dict(progress)


def bank_satisfied(
    bank: str | None,
    subjects: Sequence[Subject],
    bank_requirements: Mapping[str, int],
    progress: Mapping[str, int],
    electives_satisfied: bool,
) -> bool:
    """Si el banco (o el cupo agregado) ya no necesita créditos.

    Sin cupos oficiales por banco, decide el agregado de electivas
    (`electives_satisfied`).
    """
    if not bank_requirements:
        return electives_satisfied
    if bank and bank in bank_requirements:
        return progress.get(bank, 0) >= bank_requirements[bank]
    if bank:
        # Banco sin cupo de créditos (p.ej. práctica 0 cr):
        # satisfecho si ya cursó o cursa alguna materia del banco.
        return any((s.cursada or s.cursando) and s.elective_bank == bank for s in subjects)
    return all(progress.get(name, 0) >= req for name, req in bank_requirements.items())


def subject_status(
    subject: Subject,
    unlocked: set[str],
    satisfied: Callable[[str | None], bool],
) -> str:
    """Estado de una materia: passed, in_progress, not_needed, available o locked."""
    if subject.cursada:
        return "passed"
    if subject.cursando:
        return "in_progress"
    if all(p in unlocked for p in subject.prerequisites):
        # Una electiva solo está "disponible" si su banco (o el cupo
        # agregado) aún necesita créditos.
        if not subject.obligatoria and satisfied(subject.elective_bank):
            return "not_needed"
        return "available"
    return "locked"


def elective_banks(
    subjects: Sequence[Subject], bank_requirements: Mapping[str, int]
) -> list[ElectiveBank]:
    """Bancos de electivas ordenados por nombre."""
    bank_subjects: dict[str, list[Subject]] = defaultdict(list)
    for s in subjects:
        if s.elective_bank:
            bank_subjects[s.elective_bank].append(s)

    banks: list[ElectiveBank] = []
    for bank_name, group in sorted(bank_subjects.items()):
        required: int | None
        if bank_name in bank_requirements:
            required = bank_requirements[bank_name]
        elif bank_requirements:
            # Hay cupos oficiales pero no para este banco (p.ej. práctica): 0 = informativo.
            required = 0
        else:
            # Sin cupos oficiales el mínimo es desconocido. Sumar el catálogo lo inflaba (#6).
            required = None
        banks.append(
            ElectiveBank(
                name=bank_name,
                credits_required=required,
                credits_approved=sum(s.credits for s in group if s.cursada),
                subject_codes=[s.code for s in group],
            )
        )
    return banks


def build_record(
    *,
    student_name: str,
    program_name: str,
    program_code: str,
    pensum_version: int,
    version_actual: int,
    versiones: list[int],
    total_credits: int,
    subjects: list[Subject],
    bank_requirements: Mapping[str, int] | None = None,
    enrolled_version: int | None = None,
    enrolled_outside_pensum: Sequence[EnrolledOutsidePensum] = (),
) -> AcademicRecord:
    """Expediente con progreso, estados y bancos a partir de las materias."""
    unlocked = {s.code for s in subjects if s.cursada or s.cursando}
    requirements: Mapping[str, int] = bank_requirements or {}

    # Progreso hacia el grado: las obligatorias cuentan completas, pero las
    # electivas solo cuentan hasta lo que el programa exige.
    # Preferimos cupos oficiales por banco (pensum ayudame2); si no hay,
    # caemos al agregado total_credits - obligatorias (catálogo Cursum).
    obligatorias_total = sum(s.credits for s in subjects if s.obligatoria)
    obligatorias_passed = sum(s.credits for s in subjects if s.obligatoria and s.cursada)
    electives_passed = sum(s.credits for s in subjects if not s.obligatoria and s.cursada)
    electives_in_progress = sum(
        s.credits for s in subjects if not s.obligatoria and not s.cursada and s.cursando
    )
    progress = bank_progress(subjects)

    if requirements:
        elective_progress = sum(
            min(progress.get(name, 0), req) for name, req in requirements.items()
        )
        electives_satisfied = all(
            progress.get(name, 0) >= req for name, req in requirements.items()
        )
    else:
        electives_required = max(0, total_credits - obligatorias_total)
        elective_progress = min(electives_passed, electives_required)
        electives_satisfied = electives_passed + electives_in_progress >= electives_required

    def satisfied(bank: str | None) -> bool:
        return bank_satisfied(bank, subjects, requirements, progress, electives_satisfied)

    enriched = [
        s.model_copy(update={"status": subject_status(s, unlocked, satisfied)}) for s in subjects
    ]

    completed_credits = sum(s.credits for s in enriched if s.cursada)
    in_progress_credits = sum(s.credits for s in enriched if s.cursando and not s.cursada)
    progress_credits = min(total_credits, obligatorias_passed + elective_progress)
    graduated = progress_credits >= total_credits

    return AcademicRecord(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=pensum_version,
        version_actual=version_actual,
        enrolled_version=enrolled_version,
        versiones=versiones,
        total_credits=total_credits,
        completed_credits=completed_credits,
        progress_credits=progress_credits,
        in_progress_credits=in_progress_credits,
        graduated=graduated,
        subjects=enriched,
        elective_banks=elective_banks(enriched, requirements),
        enrolled_outside_pensum=list(enrolled_outside_pensum),
    )
