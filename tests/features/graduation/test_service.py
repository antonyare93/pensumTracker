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
