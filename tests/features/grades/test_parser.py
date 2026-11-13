from app.features.grades.parser import parse_current_grades
from app.features.grades.schemas import CourseGrades, Evaluation
from tests.fakes.portal import fixture


def test_lee_evaluaciones_porcentajes_y_notas_de_cada_materia():
    courses = parse_current_grades(fixture("notas_semestre.html"))

    assert courses == [
        CourseGrades(
            code="2540600",
            name="INGLÉS VI",
            survey_pending=True,
            evaluations=[
                Evaluation(name="PARCIAL LISTENING", percent=10, grade=None),
                Evaluation(name="OUTLINE", percent=5, grade=None),
            ],
        ),
        CourseGrades(
            code="2554615",
            name="SIMULACION DE SIST Y LABO",
            survey_pending=False,
            evaluations=[
                Evaluation(name="LAB 1 Y 2", percent=10, grade=4.7),
                Evaluation(name="LAB 4 5 Y 6", percent=15, grade=None),
                Evaluation(name="EXAMEN PARCIAL", percent=25, grade=3.5),
            ],
        ),
    ]


def test_pagina_sin_materias_devuelve_lista_vacia():
    assert parse_current_grades("<p>MIS NOTAS DEL SEMESTRE</p>") == []


def test_nota_fuera_de_rango_se_descarta():
    html = (
        '<div class="card"><div class="card-header">[1] X</div><div class="card-body">'
        '<table><tbody><tr><td class="materia_label">1) A</td><td>10</td><td>45</td></tr>'
        "</tbody></table></div></div>"
    )
    assert parse_current_grades(html)[0].evaluations == [
        Evaluation(name="A", percent=10, grade=None)
    ]
