import pytest
from pydantic import ValidationError

from app.features.record.schemas import AcademicRecord

BASE = dict(
    student_name="ANA PRUEBA",
    program_name="PRUEBA",
    program_code="506",
    pensum_version=5,
    version_actual=5,
    versiones=[5],
    total_credits=168,
    completed_credits=200,
    in_progress_credits=0,
    subjects=[],
)


def test_avance_no_puede_superar_el_total():
    with pytest.raises(ValidationError):
        AcademicRecord(**BASE, progress_credits=169)


def test_aprobados_si_pueden_superar_el_total():
    record = AcademicRecord(**BASE, progress_credits=168)
    assert record.completed_credits == 200
