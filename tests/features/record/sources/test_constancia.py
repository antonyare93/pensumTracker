from app.features.record.sources.constancia import parse_current_subjects, parse_student_info
from app.features.record.sources.models import EnrolledSubject, StudentInfo
from tests.fakes.portal import fixture


def test_student_info_de_la_fixture() -> None:
    assert parse_student_info(fixture("constancia.html")) == StudentInfo(
        student_name="ANA PRUEBA", program_name="INGENIERÍA DE PRUEBA", program_code="506"
    )


def test_student_info_vacio_sin_coincidencias() -> None:
    assert parse_student_info("<html></html>") == StudentInfo(
        student_name="", program_name="", program_code=""
    )


def test_current_subjects_de_la_fixture() -> None:
    assert parse_current_subjects(fixture("constancia.html")) == [
        EnrolledSubject(code="2000300", name="PROGRAMACIÓN DE PRUEBA")
    ]


def test_current_subjects_sin_nombre_deja_el_nombre_en_none() -> None:
    html = '<h5>MATERIAS MATRICULADAS</h5><div class="alert-success">CÓDIGO: 2000300</div>'
    assert parse_current_subjects(html) == [EnrolledSubject(code="2000300", name=None)]


def test_current_subjects_sin_h5_devuelve_lista_vacia() -> None:
    assert parse_current_subjects("<html><body><p>nada</p></body></html>") == []
