"""Tests del cálculo de progreso académico (AcademicRecordBuilder).

Usan datos sintéticos: no requieren el portal de la UdeA ni una cuenta real.
Modelo de prueba: total_credits=10, obligatorias O1+O2=8 cr,
electivas requeridas = 10-8 = 2 cr (banco "B" con E1,E2,E3 de 2 cr c/u).
"""
from models.academic import Subject
from services.academic_service import AcademicRecordBuilder

TOTAL = 10


def _subject(code, credits, obligatoria, *, cursada=False, cursando=False,
             bank=None, prereqs=None):
    return Subject(
        code=code, name=code, credits=credits, semester=1,
        obligatoria=obligatoria, elective_bank=bank,
        prerequisites=prereqs or [], cursada=cursada, cursando=cursando,
    )


def _build(subjects):
    return AcademicRecordBuilder().build(
        student_name="X", program_name="Y", program_code="506",
        pensum_version=3, version_actual=5, versiones=[3, 5],
        total_credits=TOTAL, subjects=subjects,
    )


def _statuses(record):
    return {s.code: s.status for s in record.subjects}


def test_graduado_100_y_sin_disponibles():
    """Graduado: obligatorias completas + electivas requeridas cubiertas."""
    subs = [
        _subject("O1", 4, True, cursada=True),
        _subject("O2", 4, True, cursada=True),
        _subject("E1", 2, False, cursada=True, bank="B"),
        _subject("E2", 2, False, bank="B"),
        _subject("E3", 2, False, bank="B"),
    ]
    rec = _build(subs)
    assert rec.progress_credits == TOTAL
    assert rec.graduated is True
    st = _statuses(rec)
    # ninguna materia debe quedar "disponible"
    assert [c for c, s in st.items() if s == "available"] == []
    # las electivas sobrantes quedan "no requeridas", no disponibles
    assert st["E2"] == "not_needed"
    assert st["E3"] == "not_needed"


def test_electivas_de_mas_no_pasan_de_100_y_obligatoria_pendiente_visible():
    """Cursó electivas de sobra pero le falta una obligatoria (caso real)."""
    subs = [
        _subject("O1", 4, True, cursada=True),
        _subject("O2", 4, True),  # pendiente
        _subject("E1", 2, False, cursada=True, bank="B"),
        _subject("E2", 2, False, cursada=True, bank="B"),
        _subject("E3", 2, False, cursada=True, bank="B"),
    ]
    rec = _build(subs)
    assert rec.completed_credits == 10      # todo lo aprobado (4 + 6)
    assert rec.progress_credits == 6        # 4 oblig + min(6,2) electivas
    assert rec.graduated is False
    st = _statuses(rec)
    assert st["O2"] == "available"          # la obligatoria pendiente sí se ofrece
    # ninguna electiva debe ofrecerse: el requisito ya está cubierto
    assert all(s != "available" for c, s in st.items() if c.startswith("E"))


def test_estudiante_normal_ofrece_electivas_y_obligatorias():
    """A mitad de carrera: aún faltan créditos de electivas."""
    subs = [
        _subject("O1", 4, True, cursada=True),
        _subject("O2", 4, True),
        _subject("E1", 2, False, bank="B"),
        _subject("E2", 2, False, bank="B"),
    ]
    rec = _build(subs)
    assert rec.graduated is False
    st = _statuses(rec)
    assert st["O2"] == "available"
    assert st["E1"] == "available"          # faltan electivas -> disponible
    assert st["E2"] == "available"


def test_prerrequisitos_bloquean():
    subs = [
        _subject("O1", 4, True),            # sin aprobar
        _subject("O2", 4, True, prereqs=["O1"]),
    ]
    rec = _build(subs)
    st = _statuses(rec)
    assert st["O1"] == "available"
    assert st["O2"] == "locked"             # su prerrequisito no está cumplido


def test_en_curso_cuenta_para_satisfacer_electivas():
    """Electivas en curso también cuentan para no ofrecer más de las debidas."""
    subs = [
        _subject("O1", 4, True, cursada=True),
        _subject("O2", 4, True, cursada=True),
        _subject("E1", 2, False, cursando=True, bank="B"),
        _subject("E2", 2, False, bank="B"),
    ]
    rec = _build(subs)
    st = _statuses(rec)
    assert st["E1"] == "in_progress"
    assert st["E2"] == "not_needed"         # ya hay 2 cr de electivas en curso
