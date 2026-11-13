from app.features.record.domain.credits import resolve_total_credits
from app.features.record.schemas import Subject

SUBJECTS = [
    Subject(code="A", name="A", credits=10, obligatoria=True),
    Subject(code="B", name="B", credits=8, obligatoria=True),
    Subject(code="C", name="C", credits=5, obligatoria=False, elective_bank="B"),
]


def test_version_oficial_igual_suma_obligatorias_y_minimos():
    total, banks = resolve_total_credits(200, SUBJECTS, 5, {"B": 4, "C": 3}, 5)
    assert (total, banks) == (25, {"B": 4, "C": 3})


def test_devuelve_copia_de_los_minimos():
    minimums = {"B": 4, "C": 3}
    _, banks = resolve_total_credits(200, SUBJECTS, 5, minimums, 5)
    assert banks is not minimums


def test_version_distinta_cae_al_catalogo():
    assert resolve_total_credits(200, SUBJECTS, 4, {"B": 4, "C": 3}, 5) == (200, {})


def test_minimos_vacios_caen_al_catalogo():
    assert resolve_total_credits(200, SUBJECTS, 5, {}, 5) == (200, {})


def test_version_oficial_none_cae_al_catalogo():
    assert resolve_total_credits(200, SUBJECTS, None, {"B": 4}, 5) == (200, {})


def test_registra_la_causa_cuando_no_hay_pagina_oficial(caplog):
    caplog.set_level("INFO")
    resolve_total_credits(200, SUBJECTS, None, {}, 5)
    assert "causa=sin_pagina" in caplog.text


def test_registra_la_causa_cuando_no_hay_minimos(caplog):
    caplog.set_level("INFO")
    resolve_total_credits(200, SUBJECTS, 5, {}, 5)
    assert "causa=sin_minimos" in caplog.text


def test_registra_la_causa_cuando_la_version_no_coincide(caplog):
    caplog.set_level("INFO")
    resolve_total_credits(200, SUBJECTS, 4, {"B": 4}, 5)
    assert "causa=version_distinta" in caplog.text
    assert "page_version=4 efectiva=5" in caplog.text
