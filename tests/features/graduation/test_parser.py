from app.features.graduation.parser import parse_missing
from app.features.graduation.schemas import MissingBank, MissingSubject, PendingGrade
from tests.fakes.portal import fixture


def test_lee_obligatorias_bancos_y_notas_pendientes():
    missing = parse_missing(fixture("faltantes.html"))

    assert missing is not None
    assert missing.mandatory == [
        MissingSubject(code="2567503", name="LAB INTEGRADO DE FISICA", credits=1),
        MissingSubject(code="2554615", name="SIMULACION DE SIST Y LABO", credits=4),
    ]
    assert missing.banks == [
        MissingBank(
            name="PRACTICA ACADEMICA A DISTANCIA",
            credits_required=0,
            credits_approved=0,
            credits_missing=0,
            subjects_required=1,
            subjects_approved=0,
            subjects_missing=1,
            options=[
                MissingSubject(code="2554600", name="TRABAJO DE GRADO", credits=0),
                MissingSubject(code="2554605", name="PRÁCTICA SOCIAL", credits=0),
            ],
        ),
        MissingBank(
            name="SOCIOHUMANISTICAS DISTANCIA",
            credits_required=11,
            credits_approved=8,
            credits_missing=3,
            subjects_required=None,
            subjects_approved=None,
            subjects_missing=None,
            options=[MissingSubject(code="2500001", name="ÉTICA", credits=3)],
        ),
    ]
    assert missing.pending == [
        PendingGrade(code="2554601", name="SEMESTRE DE INDUSTRIA", semester="20242")
    ]


def test_otra_pagina_devuelve_none():
    assert parse_missing("<p>LISTADO DE PROGRAMAS</p>") is None


def test_sin_faltantes_devuelve_listas_vacias():
    missing = parse_missing("<h6>MATERIAS FALTANTES PARA GRADO</h6>")
    assert missing is not None
    assert (missing.mandatory, missing.banks, missing.pending) == ([], [], [])
