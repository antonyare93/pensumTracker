"""Tests del armado del expediente (build_record y sus piezas).

Usan datos sintéticos: no requieren el portal de la UdeA ni una cuenta real.
Modelo de prueba: total_credits=10, obligatorias O1+O2=8 cr,
electivas requeridas = 10-8 = 2 cr (banco "B" con E1,E2,E3 de 2 cr c/u).
"""

from app.features.record.domain.record import bank_satisfied, build_record, elective_banks
from app.features.record.schemas import Subject

TOTAL = 10


def _subject(code, credits, obligatoria, *, cursada=False, cursando=False, bank=None, prereqs=None):
    return Subject(
        code=code,
        name=code,
        credits=credits,
        semester=1,
        obligatoria=obligatoria,
        elective_bank=bank,
        prerequisites=prereqs or [],
        cursada=cursada,
        cursando=cursando,
    )


def _build(subjects):
    return build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=3,
        version_actual=5,
        versiones=[3, 5],
        total_credits=TOTAL,
        subjects=subjects,
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
    assert rec.completed_credits == 10  # todo lo aprobado (4 + 6)
    assert rec.progress_credits == 6  # 4 oblig + min(6,2) electivas
    assert rec.graduated is False
    st = _statuses(rec)
    assert st["O2"] == "available"  # la obligatoria pendiente sí se ofrece
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
    assert st["E1"] == "available"  # faltan electivas -> disponible
    assert st["E2"] == "available"


def test_prerrequisitos_bloquean():
    subs = [
        _subject("O1", 4, True),  # sin aprobar
        _subject("O2", 4, True, prereqs=["O1"]),
    ]
    rec = _build(subs)
    st = _statuses(rec)
    assert st["O1"] == "available"
    assert st["O2"] == "locked"  # su prerrequisito no está cumplido


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
    assert st["E2"] == "not_needed"  # ya hay 2 cr de electivas en curso


def test_total_y_bancos_desde_requisitos_oficiales():
    """Cupos por banco del pensum oficial definen total y créditos_required."""
    subs = [
        _subject("O1", 100, True, cursada=True),
        _subject("O2", 45, True, cursada=True),
        _subject("A1", 4, False, cursada=True, bank="ALGO"),
        _subject("A2", 4, False, bank="ALGO"),
        _subject("A3", 4, False, bank="ALGO"),
        _subject("S1", 4, False, bank="SOCIO"),
        _subject("S2", 4, False, bank="SOCIO"),
        _subject("P1", 0, False, bank="PRACTICA"),
    ]
    # 145 oblig + 20 + 11 = 176 (ejemplo reducido)
    total = 145 + 20 + 11
    banks = {"ALGO": 20, "SOCIO": 11}
    rec = build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=3,
        version_actual=5,
        versiones=[3, 5],
        total_credits=total,
        subjects=subs,
        bank_requirements=banks,
    )
    assert rec.total_credits == total
    by_name = {b.name: b for b in rec.elective_banks}
    assert by_name["ALGO"].credits_required == 20
    assert by_name["SOCIO"].credits_required == 11
    assert by_name["PRACTICA"].credits_required == 0
    # ALGO aún no cubre 20 (solo 4) -> sigue ofreciendo electivas del banco
    st = _statuses(rec)
    assert st["A2"] == "available"
    assert st["S1"] == "available"
    assert st["P1"] == "available"


def test_banco_cubierto_marca_restantes_no_requeridas():
    subs = [
        _subject("O1", 4, True, cursada=True),
        _subject("E1", 4, False, cursada=True, bank="B"),
        _subject("E2", 4, False, cursada=True, bank="B"),
        _subject("E3", 4, False, bank="B"),
        _subject("F1", 4, False, bank="C"),
    ]
    rec = build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=3,
        version_actual=5,
        versiones=[3],
        total_credits=4 + 8 + 4,
        subjects=subs,
        bank_requirements={"B": 8, "C": 4},
    )
    st = _statuses(rec)
    assert st["E3"] == "not_needed"
    assert st["F1"] == "available"
    assert rec.progress_credits == 4 + 8  # oblig + B topado; C aún 0
    assert rec.graduated is False


def test_bank_satisfied_banco_con_cupo():
    subs = [_subject("E1", 4, False, cursada=True, bank="B")]
    reqs = {"B": 4, "C": 2}
    assert bank_satisfied("B", subs, reqs, {"B": 4}, False) is True
    assert bank_satisfied("B", subs, reqs, {"B": 3}, True) is False


def test_bank_satisfied_banco_sin_cupo():
    reqs = {"B": 4}
    cursada = [_subject("P1", 0, False, cursada=True, bank="P")]
    cursando = [_subject("P1", 0, False, cursando=True, bank="P")]
    pendiente = [_subject("P1", 0, False, bank="P")]
    assert bank_satisfied("P", cursada, reqs, {}, False) is True
    assert bank_satisfied("P", cursando, reqs, {}, False) is True
    assert bank_satisfied("P", pendiente, reqs, {}, True) is False


def test_bank_satisfied_sin_banco_exige_todos_los_cupos():
    reqs = {"B": 4, "C": 2}
    assert bank_satisfied(None, [], reqs, {"B": 4, "C": 2}, False) is True
    assert bank_satisfied(None, [], reqs, {"B": 4, "C": 1}, True) is False


def test_bank_satisfied_sin_cupos_oficiales_usa_el_agregado():
    subs = [_subject("P1", 0, False, cursada=True, bank="P")]
    assert bank_satisfied("B", subs, {}, {"B": 100}, False) is False
    assert bank_satisfied("P", subs, {}, {}, True) is True
    assert bank_satisfied(None, subs, {}, {}, True) is True


def test_elective_banks_ordenados_por_nombre():
    subs = [
        _subject("Z1", 2, False, bank="Z"),
        _subject("A1", 3, False, cursada=True, bank="A"),
        _subject("O1", 4, True),
        _subject("A2", 2, False, bank="A"),
    ]
    banks = elective_banks(subs, {"A": 4, "Z": 2})
    assert [(b.name, b.credits_required, b.credits_approved, b.subject_codes) for b in banks] == [
        ("A", 4, 3, ["A1", "A2"]),
        ("Z", 2, 0, ["Z1"]),
    ]


def test_elective_banks_banco_sin_cupo_oficial():
    subs = [
        _subject("A1", 3, False, bank="A"),
        _subject("P1", 2, False, bank="P"),
        _subject("P2", 3, False, bank="P"),
    ]
    with_reqs = {b.name: b.credits_required for b in elective_banks(subs, {"A": 3})}
    without_reqs = {b.name: b.credits_required for b in elective_banks(subs, {})}
    assert with_reqs == {"A": 3, "P": 0}
    # Sin cupos oficiales el requisito es desconocido; sumar el catálogo lo inflaba (#6).
    assert without_reqs == {"A": None, "P": None}


def test_electivas_sobrantes_no_tapan_obligatorias_faltantes():
    # Caso real 506 v3: 180 aprobados, faltan obligatorias y el avance daba 168/168.
    subs = [
        Subject(code="O1", name="O1", credits=10, obligatoria=True, cursada=True),
        Subject(code="O2", name="O2", credits=6, obligatoria=True, cursada=False),
        Subject(
            code="E1", name="E1", credits=8, obligatoria=False, elective_bank="A", cursada=True
        ),
        Subject(
            code="E2", name="E2", credits=8, obligatoria=False, elective_bank="B", cursada=True
        ),
    ]
    rec = build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=3,
        version_actual=3,
        versiones=[3],
        total_credits=20,
        subjects=subs,
        bank_requirements={"A": 8, "B": 8},
    )
    assert rec.progress_credits == 10 + 4  # electivas topadas en 20 - 16
    assert rec.graduated is False


def test_avance_no_cuenta_electivas_en_curso():
    subs = [
        Subject(code="O1", name="O1", credits=10, obligatoria=True, cursada=True),
        Subject(
            code="E1", name="E1", credits=4, obligatoria=False, elective_bank="A", cursada=True
        ),
        Subject(
            code="E2", name="E2", credits=4, obligatoria=False, elective_bank="A", cursando=True
        ),
    ]
    rec = build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=5,
        version_actual=5,
        versiones=[5],
        total_credits=18,
        subjects=subs,
        bank_requirements={"A": 8},
    )
    assert rec.progress_credits == 14
    assert rec.progress_credits <= rec.completed_credits


def _banks_record(passed: dict[str, int], requirements: dict[str, int], total: int):
    subs = [Subject(code="O", name="O", credits=10, obligatoria=True, cursada=True)]
    for bank, credits in passed.items():
        if credits:
            subs.append(
                Subject(
                    code=f"E{bank}",
                    name=bank,
                    credits=credits,
                    obligatoria=False,
                    elective_bank=bank,
                    cursada=True,
                )
            )
    for bank in requirements:
        subs.append(
            Subject(code=f"X{bank}", name=bank, credits=4, obligatoria=False, elective_bank=bank)
        )
    rec = build_record(
        student_name="X",
        program_name="Y",
        program_code="506",
        pensum_version=5,
        version_actual=5,
        versiones=[5],
        total_credits=total,
        subjects=subs,
        bank_requirements=requirements,
    )
    return {b.name: b.satisfied for b in rec.elective_banks}


def test_banco_cumplido_solo_si_llega_al_minimo():
    got = _banks_record({"A": 3, "B": 0}, {"A": 3, "B": 12}, 10 + 15)
    assert got == {"A": True, "B": False}


def test_un_enfasis_completo_cumple_los_demas_del_grupo():
    req = {"S": 3, "EA": 15, "EB": 15, "EC": 15}
    got = _banks_record({"S": 3, "EA": 15, "EB": 3}, req, 10 + 3 + 15)
    assert got == {"S": True, "EA": True, "EB": True, "EC": True}


def test_enfasis_sin_completar_no_cumple_ninguno():
    req = {"S": 3, "EA": 15, "EB": 15, "EC": 15}
    got = _banks_record({"S": 3, "EA": 6}, req, 10 + 3 + 15)
    assert got == {"S": True, "EA": False, "EB": False, "EC": False}


def test_sin_minimos_no_se_sabe():
    got = _banks_record({"A": 3}, {}, 20)
    assert got == {"A": None}
