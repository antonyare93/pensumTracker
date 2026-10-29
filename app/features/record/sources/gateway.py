"""Lectura del portal: hace las peticiones y entrega lo que devuelven los parsers."""

import logging
from typing import Protocol
from urllib.parse import urlsplit

import requests

from app.core.config import Settings, get_settings
from app.core.errors import PortalFormatChanged
from app.features.record.sources import constancia, cursum, historia, pensum_oficial
from app.features.record.sources.models import (
    CursumProgram,
    CursumSubject,
    EnrolledSubject,
    GradeRow,
    HistoriaPage,
    OfficialPensum,
    StudentInfo,
)
from app.portal import auth
from app.portal.session import PortalSession

log = logging.getLogger(__name__)

_SELECTOR_PATH = "php_programas_estudiante"
_RELOGIN = "php_relogin"


class RecordSource(Protocol):
    def student_info(self) -> StudentInfo: ...

    def current_subjects(self) -> list[EnrolledSubject]: ...

    def historia(self, program_code: str) -> HistoriaPage: ...

    def semester_grades(self, semester_code: str) -> list[GradeRow]: ...

    def official_pensum(self) -> OfficialPensum | None: ...

    def program(self, program_code: str) -> CursumProgram | None: ...

    def curriculum(self, program_code: str, version: int) -> list[CursumSubject]: ...


def _parse_json(resp: requests.Response, context: str) -> object:
    """Decodifica la respuesta como JSON o lanza 502 si el portal devolvió otra cosa
    (HTML de error, página de relogin, etc.)."""
    try:
        return resp.json()
    except ValueError:
        log.error(
            "%s: respuesta no-JSON (status=%d url=%s): %r",
            context,
            resp.status_code,
            resp.url,
            resp.text[:200],
        )
        raise PortalFormatChanged()


class PortalRecordSource:
    def __init__(self, session: PortalSession, settings: Settings | None = None) -> None:
        self._session = session
        settings = settings or get_settings()
        self._historia_url = settings.tsone_url + "/php_historia_estudiante/"
        self._constancia_url = settings.tsone_url + "/php_constancia_estudiante/"
        self._pensum_url = settings.ayudame2_url + "/php_pensum_estudiante/"
        self._ayudame2_host = urlsplit(settings.ayudame2_url).netloc
        self._cursum_url = settings.cursum_url
        self._constancia_html: str | None = None
        self._official_pensum: OfficialPensum | None = None
        self._official_pensum_loaded = False
        self._curriculum: dict[tuple[str, int], list[CursumSubject]] = {}

    def _constancia(self) -> str:
        if self._constancia_html is None:
            resp = self._session.tsone_get(self._constancia_url + "?app=consultar")
            self._constancia_html = resp.text
        return self._constancia_html

    def student_info(self) -> StudentInfo:
        return constancia.parse_student_info(self._constancia())

    def current_subjects(self) -> list[EnrolledSubject]:
        return constancia.parse_current_subjects(self._constancia())

    def historia(self, program_code: str) -> HistoriaPage:
        retorno = self._historia_url + "?app=consultar"
        resp = self._session.tsone_get(retorno)
        if _SELECTOR_PATH not in resp.url:
            return HistoriaPage(
                semester_codes=historia.parse_semester_codes(resp.text),
                selector_applied=False,
                enrolled_version=None,
            )
        log.info("historia: selector de programa detectado, seleccionando %s", program_code)
        option = historia.parse_program_selector(resp.text, program_code)
        if option is None:
            return HistoriaPage(
                semester_codes=historia.parse_semester_codes(resp.text),
                selector_applied=False,
                enrolled_version=None,
            )
        # El form2 NO se envía a su propio action (vacío): el JS (retorno.js) le
        # asigna como action la URL _retorno (la historia) y lo postea allí.
        post_resp = self._session.tsone_post(retorno, dict(option.form_data))
        if _SELECTOR_PATH not in post_resp.url:
            codes = historia.parse_semester_codes(post_resp.text)
            log.info(
                "historia: programa %s seleccionado | data-semestre=%d", program_code, len(codes)
            )
            return HistoriaPage(
                semester_codes=codes, selector_applied=True, enrolled_version=option.version
            )
        log.warning(
            "historia: la selección de %s no se aplicó (sigue en el selector)", program_code
        )
        hist_resp = self._session.tsone_get(retorno)
        return HistoriaPage(
            semester_codes=historia.parse_semester_codes(hist_resp.text),
            selector_applied=True,
            enrolled_version=option.version,
        )

    def semester_grades(self, semester_code: str) -> list[GradeRow]:
        resp = self._session.tsone_get(
            self._historia_url + f"?app=ver_semestre&semestre={semester_code}"
        )
        return historia.parse_semester_grades(resp.text)

    def official_pensum(self) -> OfficialPensum | None:
        if self._official_pensum_loaded:
            return self._official_pensum
        url = self._pensum_url + "?app=consultar"
        resp = self._session.get(url, allow_redirects=True)
        credentials = self._session.credentials
        if (_RELOGIN in resp.url or _RELOGIN in resp.text) and credentials:
            log.info("official_pensum: reauth ayudame2")
            auth.reauth(self._session, self._ayudame2_host, credentials.password.get_secret_value())
            resp = self._session.get(url, allow_redirects=True)

        pensum = None if _RELOGIN in resp.url else pensum_oficial.parse_official_pensum(resp.text)
        if pensum is None:
            log.warning("official_pensum: no se pudo leer el pensum | url=%s", resp.url)
        self._official_pensum = pensum
        self._official_pensum_loaded = True
        return pensum

    def program(self, program_code: str) -> CursumProgram | None:
        resp = self._session.get(self._cursum_url + "/programas", allow_redirects=True)
        return cursum.parse_program(_parse_json(resp, "fetch_program_info"), program_code)

    def curriculum(self, program_code: str, version: int) -> list[CursumSubject]:
        key = (program_code, version)
        cached = self._curriculum.get(key)
        if cached is not None:
            return cached
        resp = self._session.get(
            f"{self._cursum_url}/pensum/{program_code}/{version}", allow_redirects=True
        )
        log.info("curriculum: cursum status=%d url=%s", resp.status_code, resp.url)
        items = _parse_json(resp, "fetch_curriculum")
        if isinstance(items, list):
            log.info("curriculum: cursum devolvió %d materias", len(items))
            subjects = cursum.parse_curriculum(items)
        else:
            # Misma llamada en ambas ramas: el log del recuento debe salir después
            # del que emite parse_curriculum, como antes de extraer el parser.
            subjects = cursum.parse_curriculum(items)
            log.info("curriculum: cursum devolvió %d materias", 0)
        self._curriculum[key] = subjects
        return subjects
