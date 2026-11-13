import json
import logging
from collections.abc import Callable, Generator, Iterator
from typing import cast

import anyio
import pytest
import requests
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.stream import ClosingStreamingResponse, StreamContext, run_stages
from app.features.record.router import LoginRequest, build_router
from app.features.record.service import RecordStage
from app.portal.credentials import (
    LoginPerRequest,
    PortalCredentials,
    get_session_provider,
)
from app.portal.session import PortalSession
from main import app
from tests.fakes.portal import AYUDAME2, CURSUM, FakePortal, fixture, validar_url

URL = "/api/login/stream"
BODY = {"username": "usuario", "password": "clave", "pensum_version": 0}


class RecordingProvider:
    def __init__(self) -> None:
        self.sessions: list[PortalSession] = []
        self.released: list[PortalSession] = []

    def open(self, credentials: PortalCredentials) -> PortalSession:
        session = LoginPerRequest().open(credentials)
        self.sessions.append(session)
        return session

    def release(self, session: PortalSession) -> None:
        self.released.append(session)
        LoginPerRequest().release(session)


@pytest.fixture
def provider() -> Iterator[RecordingProvider]:
    recording = RecordingProvider()
    app.dependency_overrides[get_session_provider] = lambda: recording
    yield recording
    app.dependency_overrides.pop(get_session_provider, None)


def _stages(text: str) -> list[str]:
    return [json.loads(line)["stage"] for line in text.splitlines() if line.strip()]


def _abre(provider: RecordingProvider) -> PortalSession:
    return provider.open(PortalCredentials("usuario", SecretStr("clave")))


def test_stream_completo_termina_en_record_y_cierra_la_sesion(
    fake_portal: FakePortal, provider: RecordingProvider
):
    with TestClient(app) as client:
        response = client.post(URL, json=BODY)
    assert _stages(response.text)[-3:] == ["record", "grades", "missing"]
    (session,) = provider.sessions
    assert session.closed is True
    assert session.credentials is None


def test_generador_cerrado_a_medias_cierra_la_sesion(
    fake_portal: FakePortal, provider: RecordingProvider
):
    session = _abre(provider)
    ctx = StreamContext(session, 0)
    stream = cast(
        Generator[str],
        run_stages([RecordStage()], ctx, on_finish=lambda: provider.release(session)),
    )
    next(stream)
    assert session.closed is False
    stream.close()
    assert session.closed is True
    assert session.credentials is None


def test_reauth_tardio_usa_la_clave_de_la_sesion(fake_portal: FakePortal):
    pensum = f"{AYUDAME2}/php_pensum_estudiante/?app=consultar"
    calls = {"n": 0}

    def callback(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        calls["n"] += 1
        if calls["n"] == 1:
            return 200, {}, "<html>php_relogin</html>"
        return 200, {}, fixture("pensum_oficial.html")

    fake_portal._add("GET", pensum, callback=callback, content_type="text/html; charset=utf-8")
    with TestClient(app) as client:
        response = client.post(URL, json=BODY)
    assert _stages(response.text)[-3:] == ["record", "grades", "missing"]
    validar = [
        c for c in fake_portal.rsps.calls if c.request.url == validar_url("ayudame2.udea.edu.co")
    ]
    assert len(validar) == 2
    assert all(c.request.body == "clave=clave" for c in validar)


def _scope() -> dict:
    return {"type": "http", "asgi": {"version": "3.0"}, "method": "POST", "headers": []}


async def _receive_forever():
    await anyio.sleep_forever()
    return {}


def _response(provider: RecordingProvider, session: PortalSession) -> ClosingStreamingResponse:
    def release() -> None:
        provider.release(session)

    return ClosingStreamingResponse(
        run_stages([RecordStage()], StreamContext(session, 0), on_finish=release),
        media_type="application/x-ndjson",
        on_close=release,
    )


def test_corte_del_cliente_tras_el_primer_chunk_cierra_la_sesion(
    fake_portal: FakePortal, provider: RecordingProvider
):
    session = _abre(provider)
    sent: list[str] = []

    async def send(message):
        sent.append(message["type"])
        if message["type"] == "http.response.body":
            raise OSError("cliente desconectado")

    async def run():
        await _response(provider, session)(_scope(), _receive_forever, send)

    with pytest.raises(OSError):
        anyio.run(run)
    assert "http.response.body" in sent
    assert session.closed is True
    assert session.credentials is None


def test_endpoint_real_cablea_on_close_con_release(
    fake_portal: FakePortal, provider: RecordingProvider
):
    (ruta,) = [
        r for r in build_router([RecordStage()]).routes if isinstance(r, APIRoute) and r.path == URL
    ]
    endpoint = cast(Callable[..., ClosingStreamingResponse], ruta.endpoint)
    response = endpoint(LoginRequest(username="usuario", password=SecretStr("clave")), provider)
    (session,) = provider.sessions

    async def send(message):
        if message["type"] == "http.response.start":
            raise OSError("cliente desconectado")

    async def run():
        await response(_scope(), _receive_forever, send)

    with pytest.raises(OSError):
        anyio.run(run)
    # El corte llega antes del primer evento: solo on_close puede cerrar la sesión.
    assert session in provider.released
    assert session.closed is True


def test_release_tolera_doble_llamada(fake_portal: FakePortal, provider: RecordingProvider):
    session = _abre(provider)

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("cliente desconectado")

    async def run():
        await _response(provider, session)(_scope(), _receive_forever, send)

    with pytest.raises(OSError):
        anyio.run(run)
    # on_finish (finally del generador) y on_close (red de seguridad) corren los dos.
    assert provider.released.count(session) == 2
    assert session.closed is True


def test_desconexion_por_receive_cierra_la_sesion(
    fake_portal: FakePortal, provider: RecordingProvider
):
    session = _abre(provider)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    async def run():
        await _response(provider, session)(_scope(), receive, send)

    anyio.run(run)
    assert session.closed is True
    assert session.credentials is None


def test_respuesta_sin_iterar_cierra_la_sesion(
    fake_portal: FakePortal, provider: RecordingProvider
):
    session = _abre(provider)

    async def send(message):
        raise OSError("cliente desconectado")

    async def run():
        await _response(provider, session)(_scope(), _receive_forever, send)

    with pytest.raises(OSError):
        anyio.run(run)
    assert session.closed is True
    assert session.credentials is None


def test_error_de_red_en_stream_conserva_la_causa(fake_portal: FakePortal, caplog):
    fake_portal.override("GET", f"{CURSUM}/pensum/506/5", body=requests.ReadTimeout())
    with caplog.at_level(logging.WARNING, logger="app.core.stream"):
        with TestClient(app) as client:
            client.post(URL, json=BODY)
    records = [r for r in caplog.records if "durante el streaming" in r.getMessage()]
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert "ReadTimeout" in caplog.text


@pytest.mark.parametrize(
    "path", ["/api/login", "/api/session", "/api/academic-record", "/api/academic-record/stream"]
)
def test_endpoints_viejos_no_existen(path: str):
    with TestClient(app) as client:
        assert client.post(path, json=BODY).status_code == 404


def test_password_no_aparece_en_el_repr():
    assert "clave" not in repr(LoginRequest(username="u", password=SecretStr("clave")))
