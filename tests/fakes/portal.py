"""Portal UdeA falso para pruebas: registra en un RequestsMock todas las URLs que
PortalScraper pide durante el login y el stream, con páginas inventadas.

Toda URL va con coincidencia exacta de query string. Además, las peticiones que
importan llevan matchers sobre lo que el cliente envía (formularios, headers y la
cookie udeasecure). Lo que el scraper pida y no esté registrado, o no cumpla los
matchers, falla con ConnectionError de responses.
"""

import json
from collections.abc import Callable, Mapping
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import responses
from requests import PreparedRequest
from responses import matchers

TSONE = "https://tsone.udea.edu.co"
AYUDAME2 = "https://ayudame2.udea.edu.co"
CURSUM = "https://wsingenieria.udea.edu.co:8094/cursum/ingenieria"
SSO = f"{AYUDAME2}/php_mua_externos/"

HISTORIA = f"{TSONE}/php_historia_estudiante/"
CONSTANCIA = f"{TSONE}/php_constancia_estudiante/"
PENSUM = f"{AYUDAME2}/php_pensum_estudiante/"
NOTAS = f"{TSONE}/php_notas_estudiante/"
FALTANTES = f"{AYUDAME2}/php_materias_faltantes_estudiante/"
SELECTOR = (
    f"{TSONE}/php_programas_estudiante/"
    "?app=listar"
    "&tipos=MAESTRIA,PREGRADO,DOCTORAD,ESPECIAL,PREPARAT,E-FLEXIB,SIGUEME,EXTENSIO"
    "&estados=ACTIVO,DESERTOR,CANCELO%20SEM,ADMITIDO,GRADUADO,TERMINOMATERIAS"
    "&canal=post&retorno=historia"
)

HOSTS = ("tsone.udea.edu.co", "ayudame2.udea.edu.co")
SEMESTRES = ("20241", "20242")
PENSUM_VERSIONES = (3, 5)

USUARIO = "usuario"
CLAVE = "clave"

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "portal"
HTML = "text/html; charset=utf-8"

Matcher = Callable[[PreparedRequest], tuple[bool, str]]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def validar_url(host: str) -> str:
    return f"https://{host}/php_relogin/?app=validar"


def _matcher_for(url: str) -> list[Matcher]:
    """Query string exacto: el de la URL, o ninguno si la URL no lleva."""
    query = urlsplit(url).query
    if not query:
        return [matchers.query_param_matcher({})]
    return [matchers.query_string_matcher(query)]


def _cookie(request: PreparedRequest, name: str) -> str | None:
    jar: SimpleCookie = SimpleCookie()
    jar.load(request.headers.get("Cookie", ""))
    morsel = jar.get(name)
    return None if morsel is None else morsel.value


def form_contains(params: Mapping[str, str]) -> Matcher:
    """El form urlencoded trae al menos estos pares; los demás campos no importan."""

    def match(request: PreparedRequest) -> tuple[bool, str]:
        body = request.body or ""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        sent = dict(parse_qsl(body, keep_blank_values=True))
        missing = {k: v for k, v in params.items() if sent.get(k) != v}
        if missing:
            return False, f"form sin {missing} (enviado: {sorted(sent)})"
        return True, ""

    return match


def _key(method: str, url: str) -> tuple[str, str]:
    return method.upper(), url


class FakePortal:
    def __init__(
        self,
        rsps: responses.RequestsMock,
        *,
        multi_program: bool = False,
        validar_ok: bool = True,
    ) -> None:
        self.rsps = rsps
        self.multi_program = multi_program
        self.validar_ok = validar_ok
        # Último hash entregado por un validar exitoso. Es el valor que el cliente
        # debe mandar en la cookie udeasecure a tsone (None antes del primer reauth).
        self.udeasecure: str | None = None
        self._registered: dict[tuple[str, str], responses.BaseResponse] = {}
        self._request_matchers: dict[tuple[str, str], list[Matcher]] = {}
        self._register_all()

    def udeasecure_matcher(self, request: PreparedRequest) -> tuple[bool, str]:
        """La cookie udeasecure coincide con el último hash que entregó el portal."""
        sent = _cookie(request, "udeasecure")
        if sent == self.udeasecure:
            return True, ""
        return False, f"udeasecure={sent!r}, se esperaba {self.udeasecure!r}"

    def _add(
        self,
        method: str,
        url: str,
        *,
        match: list[Matcher] | None = None,
        callback: Callable[[PreparedRequest], tuple[int, dict[str, str], str]] | None = None,
        **kwargs: Any,
    ) -> None:
        key = _key(method, url)
        old = self._registered.pop(key, None)
        if old is not None:
            # Por identidad: rsps.remove() compara solo método y URL base, y se
            # llevaría las demás queries de la misma ruta (ingreso y validar).
            registered = self.rsps.get_registry().registered
            registered[:] = [r for r in registered if r is not old]
        if match is not None:
            self._request_matchers[key] = match
        all_matchers = _matcher_for(url) + self._request_matchers.get(key, [])
        base = url.split("?", 1)[0]
        response: responses.BaseResponse
        if callback is not None:
            response = responses.CallbackResponse(
                method=method.upper(), url=base, callback=callback, match=all_matchers, **kwargs
            )
        else:
            response = responses.Response(
                method=method.upper(), url=base, match=all_matchers, **kwargs
            )
        self.rsps.add(response)
        self._registered[key] = response

    def _html(self, method: str, url: str, name: str, **kwargs: Any) -> None:
        self._add(method, url, body=fixture(name), content_type=HTML, **kwargs)

    def _validar(self, host: str) -> Callable[[PreparedRequest], tuple[int, dict[str, str], str]]:
        def callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
            if not self.validar_ok:
                return 200, {}, json.dumps({"error": "clave"})
            self.udeasecure = f"hash-{host}"
            return 200, {}, json.dumps({"hash": self.udeasecure})

        return callback

    def _register_all(self) -> None:
        self._add(
            "POST",
            SSO,
            body="<html><body>ok</body></html>",
            content_type=HTML,
            match=[matchers.urlencoded_params_matcher({"usuario": USUARIO, "clave": CLAVE})],
        )

        tsone_cookie: list[Matcher] = [self.udeasecure_matcher]
        historia = f"{HISTORIA}?app=consultar"
        if self.multi_program:
            self._add(
                "GET",
                historia,
                status=302,
                headers={"Location": SELECTOR},
                match=tsone_cookie,
            )
            self._html("GET", SELECTOR, "selector_programas.html")
            self._html(
                "POST",
                historia,
                "historia.html",
                match=[form_contains({"programa": "506", "version": "3"})],
            )
        else:
            self._html("GET", historia, "historia.html", match=tsone_cookie)
            self._html("POST", historia, "historia.html")

        for host in HOSTS:
            relogin = f"https://{host}/php_relogin/"
            self._add("POST", f"{relogin}?app=ingreso", body="", content_type=HTML)
            self._add(
                "POST",
                validar_url(host),
                callback=self._validar(host),
                content_type="application/json",
                match=[
                    matchers.urlencoded_params_matcher({"clave": CLAVE}),
                    matchers.header_matcher(
                        {"X-Requested-With": "XMLHttpRequest"}, strict_match=False
                    ),
                ],
            )
            end = f"https://{host}/php_libs/reauthenticate_end.php?hash=hash-{host}"
            self._add(
                "GET",
                end,
                body=fixture("reauth_end.html").replace("__HOST__", host),
                content_type=HTML,
            )
            self._add("POST", f"https://{host}/php_libs/fin.php", body="", content_type=HTML)

        self._html("GET", f"{CONSTANCIA}?app=consultar", "constancia.html", match=tsone_cookie)
        for sem in SEMESTRES:
            self._html(
                "GET",
                f"{HISTORIA}?app=ver_semestre&semestre={sem}",
                f"semestre_{sem}.html",
                match=tsone_cookie,
            )
        self._html("GET", f"{PENSUM}?app=consultar", "pensum_oficial.html")
        self._html("GET", f"{NOTAS}?app=consultar", "notas_semestre.html")
        self._html("GET", f"{FALTANTES}?app=consultar", "faltantes.html")

        self._add(
            "GET",
            f"{CURSUM}/programas",
            body=fixture("cursum_programas.json"),
            content_type="application/json",
        )
        for version in PENSUM_VERSIONES:
            self.add_cursum_pensum(version)

    def add_cursum_pensum(self, version: int) -> None:
        """Registra /pensum/506/{version} con el JSON de prueba."""
        self._add(
            "GET",
            f"{CURSUM}/pensum/506/{version}",
            body=fixture("cursum_pensum_506.json"),
            content_type="application/json",
        )

    def override(
        self,
        method: str,
        url: str,
        *,
        body: str | bytes | Exception | None = None,
        json: object | None = None,
        status: int = 200,
    ) -> None:
        """Reemplaza la respuesta registrada para method+url (o la agrega si no existía).

        Los matchers de la petición (formularios, headers, cookie) se conservan:
        override cambia lo que responde el portal, no lo que el cliente debe enviar.
        body puede ser una excepción: responses la lanza al recibir la petición.
        """
        kwargs: dict[str, Any] = {"status": status}
        if json is not None:
            kwargs["json"] = json
        else:
            kwargs["body"] = "" if body is None else body
            if isinstance(body, str):
                kwargs["content_type"] = HTML
        self._add(method, url, **kwargs)
