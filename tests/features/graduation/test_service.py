from typing import cast

from app.core.stream import StreamContext
from app.features.graduation.service import MissingStage
from app.features.record.schemas import AcademicRecord
from app.portal.session import PortalSession
from tests.fakes.portal import fixture


def _ctx(record: object) -> StreamContext:
    ctx = StreamContext(session=cast(PortalSession, object()), requested_version=0)
    ctx.results["record"] = record
    return ctx


def _record() -> AcademicRecord:
    return AcademicRecord.model_construct(program_code="506")


def test_emite_los_faltantes_del_programa_del_expediente():
    calls: list[str] = []

    def fetch(_session: PortalSession, program_code: str) -> str:
        calls.append(program_code)
        return fixture("faltantes.html")

    (event,) = list(MissingStage(fetch=fetch).run(_ctx(_record())))

    assert calls == ["506"]
    assert event["stage"] == "missing"
    data = cast(dict[str, list[object]], event["data"])
    assert len(data["mandatory"]) == 2


def test_sin_expediente_no_consulta():
    def fetch(_session: PortalSession, _code: str) -> str:
        raise AssertionError("no debía consultar")

    assert list(MissingStage(fetch=fetch).run(_ctx(None))) == []


def test_pagina_ilegible_no_emite():
    stage = MissingStage(fetch=lambda _s, _c: "<p>otra cosa</p>")
    assert list(stage.run(_ctx(_record()))) == []


def test_diagnostico_compara_bancos_sin_datos_del_estudiante():
    from app.features.graduation.diagnostics import bank_diagnostics
    from app.features.graduation.schemas import MissingBank, MissingForGraduation
    from app.features.record.schemas import ElectiveBank

    record = AcademicRecord.model_construct(
        student_name="ANA PRUEBA",
        program_code="506",
        pensum_version=5,
        enrolled_version=3,
        total_credits=168,
        progress_credits=120,
        completed_credits=130,
        elective_banks=[
            ElectiveBank(
                name="ÉNFASIS A", credits_required=6, credits_approved=0, subject_codes=[]
            ),
            ElectiveBank(name="FÍSICA", credits_required=3, credits_approved=0, subject_codes=[]),
        ],
    )
    portal_bank = MissingBank(
        name="FÍSICA",
        credits_required=3,
        credits_approved=0,
        credits_missing=3,
        subjects_required=None,
        subjects_approved=None,
        subjects_missing=None,
        options=[],
    )
    missing = MissingForGraduation(mandatory=[], banks=[portal_bank], pending=[])

    line = bank_diagnostics(record, missing)

    assert "ANA" not in line
    assert "programa=506 version=5 asignada=3" in line
    assert "total=168 avance=120 aprobados=130" in line
    assert "ÉNFASIS A: nuestro=0/6 portal=ausente" in line
    assert "FÍSICA: nuestro=0/3 portal=0/3 faltan=3" in line
