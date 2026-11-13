from app.features.record.sources.models import OfficialPensum
from app.features.record.sources.pensum_oficial import parse_official_pensum
from tests.fakes.portal import fixture


def test_lee_version_y_minimos_por_banco():
    assert parse_official_pensum(fixture("pensum_oficial.html")) == OfficialPensum(
        version=5, bank_minimums={"BANCO HUMANIDADES": 4, "BANCO TÉCNICO": 3}
    )


def test_sin_encabezado_del_pensum_devuelve_none():
    assert parse_official_pensum("<p>otra cosa</p>") is None


def test_sin_version_la_version_es_none():
    html = (
        "<p>PÉNSUM DEL PROGRAMA</p><p>BANCO TÉCNICO (3 materias)</p>"
        "<p>Debes cursar al menos 3 créditos</p>"
    )
    assert parse_official_pensum(html) == OfficialPensum(
        version=None, bank_minimums={"BANCO TÉCNICO": 3}
    )


def test_banco_con_parentesis_coma_y_barra_se_lee_completo():
    html = (
        "<p>PÉNSUM DEL PROGRAMA</p><p>Programa: [506] INGENIERIA (v5)</p>"
        "<p>CURSO ALTERNATIVO DE FÍSICA (A/B), II (2 materias)</p>"
        "<p>Debes cursar al menos 6 créditos</p>"
    )
    result = parse_official_pensum(html)
    assert result is not None
    assert result.bank_minimums == {"CURSO ALTERNATIVO DE FÍSICA (A/B), II": 6}
