"""Etapa grades del stream: notas de las materias en curso.

Es opcional: si el portal falla, el expediente ya salió y el front deja la
calculadora vacía para llenarla a mano.
"""

import logging
from collections.abc import Callable, Iterator

from app.core.config import get_settings
from app.core.stream import Event, StreamContext
from app.features.grades.parser import parse_current_grades
from app.portal.session import PortalSession

log = logging.getLogger(__name__)

Fetch = Callable[[PortalSession], str]


def fetch_grades_page(session: PortalSession) -> str:
    url = get_settings().tsone_url + "/php_notas_estudiante/?app=consultar"
    return session.tsone_get(url).text


class GradesStage:
    name = "grades"
    optional = True

    def __init__(self, fetch: Fetch = fetch_grades_page) -> None:
        self._fetch = fetch

    def run(self, ctx: StreamContext) -> Iterator[Event]:
        courses = parse_current_grades(self._fetch(ctx.session))
        log.info(
            "grades: materias=%d con_encuesta_pendiente=%d",
            len(courses),
            sum(c.survey_pending for c in courses),
        )
        yield {"stage": "grades", "data": {"courses": [c.model_dump() for c in courses]}}
