"""Etapa missing del stream: materias faltantes para grado según el portal.

Es opcional y va después del expediente: necesita el código del programa para
elegirlo cuando el estudiante tiene varios.
"""

import logging
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.core.stream import Event, StreamContext
from app.features.graduation.parser import parse_missing
from app.features.record.schemas import AcademicRecord
from app.features.record.sources.historia import parse_program_selector
from app.portal import auth
from app.portal.session import PortalSession

log = logging.getLogger(__name__)

_RELOGIN = "php_relogin"
_SELECTOR = "LISTADO DE PROGRAMAS"

Fetch = Callable[[PortalSession, str], str]


def fetch_missing_page(session: PortalSession, program_code: str) -> str:
    base = get_settings().ayudame2_url
    url = base + "/php_materias_faltantes_estudiante/?app=consultar"
    resp = session.get(url, allow_redirects=True)
    credentials = session.credentials
    if (_RELOGIN in resp.url or _RELOGIN in resp.text) and credentials:
        auth.reauth(session, urlsplit(base).netloc, credentials.password.get_secret_value())
        resp = session.get(url, allow_redirects=True)
    if _SELECTOR in resp.text:
        option = parse_program_selector(resp.text, program_code)
        if option is not None:
            resp = session.post(url, data=dict(option.form_data), allow_redirects=True)
    return resp.text


class MissingStage:
    name = "missing"
    optional = True

    def __init__(self, fetch: Fetch = fetch_missing_page) -> None:
        self._fetch = fetch

    def run(self, ctx: StreamContext) -> Iterator[Event]:
        record = ctx.results.get("record")
        if not isinstance(record, AcademicRecord):
            return
        missing = parse_missing(self._fetch(ctx.session, record.program_code))
        if missing is None:
            log.warning("missing: la página de faltantes no se pudo leer")
            return
        log.info(
            "missing: obligatorias=%d bancos=%d pendientes=%d",
            len(missing.mandatory),
            len(missing.banks),
            len(missing.pending),
        )
        yield {"stage": "missing", "data": missing.model_dump()}
