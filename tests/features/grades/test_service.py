from typing import cast

from app.core.stream import StreamContext
from app.features.grades.service import GradesStage
from app.portal.session import PortalSession
from tests.fakes.portal import fixture


def test_emite_las_notas_de_las_materias_en_curso():
    stage = GradesStage(fetch=lambda _session: fixture("notas_semestre.html"))
    ctx = StreamContext(session=cast(PortalSession, object()), requested_version=0)

    (event,) = list(stage.run(ctx))

    assert event["stage"] == "grades"
    courses = cast(dict[str, list[dict[str, object]]], event["data"])["courses"]
    assert [c["code"] for c in courses] == ["2540600", "2554615"]
    assert courses[1]["evaluations"][0] == {"name": "LAB 1 Y 2", "percent": 10.0, "grade": 4.7}


def test_es_opcional():
    assert GradesStage.optional is True
