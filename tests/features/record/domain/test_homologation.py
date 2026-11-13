import pytest

from app.features.record.domain.grades import PassedSubject
from app.features.record.domain.homologation import homologate, normalize_name, restore_full_names


def _p(code, name, grade=None):
    return PassedSubject(code, name, grade)


def _passed(*items):
    return {p.code: p for p in items}


V5 = {
    "2517450": "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL",
    "2508101": "PROGRAMACIÓN I",
}


def test_catedra_renombrada_se_homologa():
    passed = _passed(_p("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"))
    assert homologate(passed, V5) == {"2517450": None}


def test_catedra_homologa_en_los_dos_sentidos():
    catalog = {"2517350": "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"}
    passed = _passed(_p("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL", 4.2))
    assert homologate(passed, catalog) == {"2517350": 4.2}


def test_alias_no_desplaza_a_la_coincidencia_directa():
    catalog = {
        "2517362": "FORMACIÓN CIUDADANA Y CONSTITUCIONAL",
        "2517450": "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL",
    }
    passed = _passed(_p("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"))
    assert homologate(passed, catalog) == {"2517362": None}


def test_ingles_sigue_homologando():
    passed = _passed(_p("2517103", "INGLÉS III", 3.8))
    assert homologate(passed, {"2599999": "ENGLISH 3"}) == {"2599999": 3.8}


def test_codigo_identico_no_pasa_por_el_nombre():
    passed = _passed(_p("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL", 4.0))
    assert homologate(passed, V5) == {}


def test_materia_ajena_no_se_homologa():
    passed = _passed(_p("2504520", "COMPORTAMIENTO QUÍMICO DE LOS MATERIALES", 4.0))
    assert homologate(passed, V5) == {}


def test_nombre_vacio_se_salta():
    passed = _passed(_p("1", "DE LA", 4.0))
    assert homologate(passed, {"2": "DE LA"}) == {}


def test_dos_codigos_viejos_con_el_mismo_nombre_gana_el_primero():
    passed = _passed(
        _p("OLD1", "PROGRAMACIÓN I", 3.5),
        _p("OLD2", "PROGRAMACION I", 4.5),
    )
    assert homologate(passed, {"2508101": "PROGRAMACIÓN I"}) == {"2508101": 3.5}


@pytest.mark.parametrize(
    "a, b",
    [
        ("CONTROL ESTADÍSTICO DE CALIDAD", "CONTROL ESTADÍSTICO DE LA CALIDAD"),
        ("ESCULTURA CONTEMPORÁNEA EN LA INGENIERÍA", "LA ESCULTURA CONTEMPORÁNEA EN LA INGENIERÍA"),
        (
            "GENIUS OF THE INDUSTRY(HISTORY OF THE GREAT INVENTIONS)",
            "GENIUS OF THE INDUSTRY (HISTORY OF THE GREAT INVENTIONS)",
        ),
        ("SOCIO-HUMANÍSTICA III", "SOCIO HUMANISTICA III"),
        (
            "AUTOCUIDADO,SALUD PÚBLICA, SEGURIDAD INDUSTRIAL Y ATENCIÓN DE EMERGENCIAS",
            "AUTOCUIDADO, SALUD PÚBLICA, SEGURIDAD INDUSTRIAL Y ATENCIÓN DE EMERGENCIAS",
        ),
        (
            "FORMACION CIUDADANA Y CONSTITUCIONAL (TURBO)",
            "FORMACION CIUDADANA Y CONSTITUCIONAL- TURBO",
        ),
        ("ARQUITECTURA DE SOFTWARE", "ARQUITECTURA DEL SOFTWARE"),
    ],
)
def test_variantes_de_redaccion_dan_la_misma_clave(a, b):
    assert normalize_name(a) == normalize_name(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("TERMODINÁMICA I", "TERMODINÁMICA II"),
        ("SOCIO-HUMANÍSTICA I", "SOCIO-HUMANÍSTICA II"),
        ("COMPORTAMIENTO QUÍMICO DE LOS MATERIALES", "COMPORTAMIENTO MECÁNICO DE LOS MATERIALES"),
        ("LAB ELECTRÓNICA BÁSICA", "ELECTRÓNICA BÁSICA"),
        ("GEOPOLÍTICA MUNDIAL (ESPAÑOL)", "GEOPOLÍTICA MUNDIAL (INGLÉS)"),
        ("FORMACIÓN CIUDADANA Y CONSTITUCIONAL", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
    ],
)
def test_materias_distintas_no_colapsan(a, b):
    assert normalize_name(a) != normalize_name(b)


def test_restaura_el_nombre_completo_que_la_historia_corta():

    passed = {
        "2566350": PassedSubject(code="2566350", name="FORMACIÓN CIUDAD Y CONSTI", grade=4.0),
        "9999999": PassedSubject(code="9999999", name="SIN CATALOGO", grade=3.5),
    }
    viejo = {"2566350": "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"}

    restored = restore_full_names(passed, [viejo])

    assert restored["2566350"].name == "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"
    assert restored["2566350"].grade == 4.0
    assert restored["9999999"].name == "SIN CATALOGO"


def test_con_nombre_completo_homologa_formacion_ciudadana_a_la_v5():

    passed = {"2566350": PassedSubject(code="2566350", name="FORMACIÓN CIUDAD Y CONSTI", grade=4.0)}
    v3 = {"2566350": "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"}
    v5 = {"2517450": "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"}

    assert homologate(passed, v5) == {}
    assert homologate(restore_full_names(passed, [v3]), v5) == {"2517450": 4.0}


@pytest.mark.parametrize(
    ("v3", "v5"),
    [
        ("ARQUITECTURA DE  COMPUTADORES Y LABORATO", "ARQUITECTURA DE COMPUTADORES Y LABORATORIO"),
        ("PROY INTEGRADOR II AREA ELECTIVA", "PROYECTO INTEGRADOR II - ÁREA ELECTIVA"),
    ],
)
def test_equivalencias_506_v3_a_v5(v3, v5):
    passed = {"OLD": PassedSubject(code="OLD", name=v3, grade=4.0)}
    assert homologate(passed, {"NEW": v5}) == {"NEW": 4.0}
