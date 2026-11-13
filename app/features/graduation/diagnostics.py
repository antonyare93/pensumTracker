"""Línea de diagnóstico que compara nuestros bancos con los faltantes del portal.

Solo lleva números y nombres de bancos del pensum: nada que identifique al estudiante.
"""

from app.features.graduation.schemas import MissingBank, MissingForGraduation
from app.features.record.schemas import AcademicRecord, ElectiveBank


def _ours(bank: ElectiveBank) -> str:
    required = "?" if bank.credits_required is None else str(bank.credits_required)
    return f"{bank.credits_approved}/{required}"


def _portal(bank: MissingBank | None) -> str:
    if bank is None:
        return "ausente"
    text = f"{bank.credits_approved}/{bank.credits_required} faltan={bank.credits_missing}"
    if bank.subjects_missing:
        text += f" materias_faltan={bank.subjects_missing}"
    return text


def bank_diagnostics(record: AcademicRecord, missing: MissingForGraduation) -> str:
    portal = {b.name: b for b in missing.banks}
    ours = [b.name for b in record.elective_banks]
    banks = [
        f"{b.name}: nuestro={_ours(b)} portal={_portal(portal.get(b.name))}"
        for b in record.elective_banks
    ]
    only_portal = [f"{name}: {_portal(b)}" for name, b in portal.items() if name not in ours]
    return (
        f"programa={record.program_code} version={record.pensum_version} "
        f"asignada={record.enrolled_version} | "
        f"total={record.total_credits} avance={record.progress_credits} "
        f"aprobados={record.completed_credits} | "
        f"obligatorias_faltan={len(missing.mandatory)} | "
        f"bancos=[{'; '.join(banks)}] | solo_portal=[{'; '.join(only_portal)}]"
    )
