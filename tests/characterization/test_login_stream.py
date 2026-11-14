import json
import re
from collections.abc import Callable

import httpx2
import requests
from fastapi.testclient import TestClient

from main import app
from tests.characterization.snapshot import assert_matches_snapshot, json_snapshot
from tests.fakes.portal import (
    AYUDAME2,
    CONSTANCIA,
    CURSUM,
    HISTORIA,
    PENSUM,
    SSO,
    FakePortal,
    fixture,
    validar_url,
)

URL = "/api/login/stream"
BODY = {"username": "usuario", "password": "clave", "pensum_version": 0}
LOGIN_FALLIDO = "Credenciales inválidas o sesión no establecida"

PortalFactory = Callable[..., FakePortal]


def _events(text: str) -> list[dict]:
    """Eventos del expediente. Las etapas grades y missing van después y tienen sus pruebas."""
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [e for e in events if e["stage"] not in ("grades", "missing")]


def _stages(events: list[dict]) -> list[str]:
    return [e["stage"] for e in events]


def _stream(body: dict | None = None) -> httpx2.Response:
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.post(URL, json=body or BODY)


def _assert_stream_headers(response: httpx2.Response) -> None:
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def _subject(event: dict, code: str | int) -> dict:
    """Materia con ese código en un evento pensum o record."""
    return next(x for x in event["data"]["subjects"] if x["code"] == str(code))


def _subject_by_name(event: dict, name: str) -> dict:
    return next(x for x in event["data"]["subjects"] if x["name"] == name)


def test_programa_unico(fake_portal_factory: PortalFactory):
    fake_portal_factory()
    response = _stream()
    _assert_stream_headers(response)
    events = _events(response.text)
    assert _stages(events) == [
        "student_info",
        "program_info",
        "pensum",
        "pensum",
        "record",
    ]
    record = events[-1]
    alias = _subject(record, 2517450)
    assert alias["cursada"] is True
    assert alias["nota"] is None
    assert _subject(record, 2000300)["status"] == "in_progress"
    assert _subject(record, 2000500)["status"] == "locked"
    assert _subject(record, 2000400)["status"] == "available"
    # El total es el del catálogo: nunca se infla con los mínimos de ayudame2.
    assert record["data"]["total_credits"] == 30
    assert record["data"]["progress_credits"] <= 30
    assert_matches_snapshot("programa_unico.ndjson", response.text)


def test_varios_programas(fake_portal_factory: PortalFactory):
    fake_portal_factory(multi_program=True)
    response = _stream()
    _assert_stream_headers(response)
    events = _events(response.text)
    infos = [e for e in events if e["stage"] == "program_info"]
    assert len(infos) == 1
    assert infos[0]["data"]["pensum_version"] == 3
    assert infos[0]["data"]["enrolled_version"] == 3
    assert infos[0]["data"]["total_credits"] == 30
    electiva = _subject_by_name(events[-1], "ELECTIVA VIEJA A")
    assert electiva["cursada"] is True
    assert electiva["nota"] == 3.8
    assert_matches_snapshot("varios_programas.ndjson", response.text)


def test_version_pedida(fake_portal_factory: PortalFactory):
    fake_portal_factory()
    response = _stream({**BODY, "pensum_version": 5})
    _assert_stream_headers(response)
    infos = [e for e in _events(response.text) if e["stage"] == "program_info"]
    assert infos[0]["data"]["pensum_version"] == 5
    assert_matches_snapshot("version_pedida.ndjson", response.text)


def test_login_fallido(fake_portal_factory: PortalFactory):
    fake_portal_factory(validar_ok=False)
    response = _stream()
    assert response.status_code == 401
    assert response.json()["detail"] == LOGIN_FALLIDO
    assert_matches_snapshot("login_fallido.json", json_snapshot(response))


def test_login_timeout(fake_portal: FakePortal):
    fake_portal.override("POST", SSO, body=requests.ConnectTimeout())
    response = _stream()
    assert response.status_code == 500
    assert_matches_snapshot("login_timeout.json", json_snapshot(response))


def test_cursum_sin_json(fake_portal: FakePortal):
    fake_portal.override("GET", f"{CURSUM}/programas", body="<html>error</html>")
    response = _stream()
    events = _events(response.text)
    assert events[-1] == {
        "stage": "error",
        "status": 502,
        "detail": "El portal de la UdeA no devolvió una respuesta válida",
    }
    assert_matches_snapshot("cursum_sin_json.ndjson", response.text)


def test_timeout_en_stream(fake_portal: FakePortal):
    fake_portal.override("GET", f"{CURSUM}/pensum/506/5", body=requests.ReadTimeout())
    response = _stream()
    events = _events(response.text)
    assert _stages(events) == ["student_info", "program_info", "error"]
    assert events[-1]["status"] == 500
    assert events[-1]["detail"] == "Error inesperado al obtener el pensum"
    assert_matches_snapshot("timeout_en_stream.ndjson", response.text)


def test_clave_faltante(fake_portal: FakePortal):
    items = json.loads(fixture("cursum_pensum_506.json"))
    del items[0]["creditos"]
    fake_portal.override("GET", f"{CURSUM}/pensum/506/5", json=items)
    response = _stream()
    events = _events(response.text)
    assert events[-1]["stage"] == "error"
    assert events[-1]["status"] == 500
    assert_matches_snapshot("clave_faltante.ndjson", response.text)


def test_reauth_ayudame2_fallido(fake_portal: FakePortal):
    """ayudame2 rechaza el reauth y el pensum oficial pide relogin: no hay mínimos
    por banco ni versión de página, así que la versión cae a versionActual de
    Cursum y el total se queda en creditosGrado."""
    fake_portal.override("POST", validar_url("ayudame2.udea.edu.co"), json={"error": "clave"})
    fake_portal.override(
        "GET",
        f"{PENSUM}?app=consultar",
        body=f'<html><body><a href="{AYUDAME2}/php_relogin/">php_relogin</a></body></html>',
    )
    response = _stream()
    events = _events(response.text)
    assert events[-1]["stage"] == "record"
    infos = [e for e in events if e["stage"] == "program_info"]
    assert len(infos) == 1
    assert infos[0]["data"]["pensum_version"] == 5
    assert infos[0]["data"]["enrolled_version"] is None
    assert infos[0]["data"]["total_credits"] == 30
    assert events[-1]["data"]["total_credits"] == 30
    assert fake_portal.udeasecure == "hash-tsone.udea.edu.co"
    assert_matches_snapshot("reauth_ayudame2_fallido.ndjson", response.text)


def test_sso_no_200(fake_portal: FakePortal):
    fake_portal.override("POST", SSO, status=500)
    response = _stream()
    assert response.status_code == 401
    assert response.json()["detail"] == LOGIN_FALLIDO
    assert_matches_snapshot("sso_no_200.json", json_snapshot(response))


def test_sesion_no_valida(fake_portal: FakePortal):
    """La historia dice que no hay usuario conectado. La primera GET de historia en
    login ignora el contenido; validate_session lo lee y el login falla con 401."""
    fake_portal.override(
        "GET",
        f"{HISTORIA}?app=consultar",
        body="<html><body>No hay usuario conectado</body></html>",
    )
    response = _stream()
    assert response.status_code == 401
    assert response.json()["detail"] == LOGIN_FALLIDO
    assert_matches_snapshot("sesion_no_valida.json", json_snapshot(response))


def test_constancia_sin_matriculadas(fake_portal: FakePortal):
    sin_h5 = re.sub(r"\s*<h5>.*?</h5>", "", fixture("constancia.html"))
    assert "<h5>" not in sin_h5
    fake_portal.override("GET", f"{CONSTANCIA}?app=consultar", body=sin_h5)
    response = _stream()
    events = _events(response.text)
    assert events[-1]["stage"] == "record"
    assert all(s["status"] != "in_progress" for s in events[-1]["data"]["subjects"])
    assert_matches_snapshot("constancia_sin_matriculadas.ndjson", response.text)


def test_programa_ausente(fake_portal: FakePortal):
    """Cursum no lista el 506: versión vigente 0, sin versiones y total de catálogo
    0. La versión sale del pensum oficial (v5) y el total de sus mínimos por banco."""
    fake_portal.override(
        "GET",
        f"{CURSUM}/programas",
        json=[{"codigo": 999, "versionActual": 2, "versiones": "1,2", "creditosGrado": 99}],
    )
    response = _stream()
    events = _events(response.text)
    assert events[-1]["stage"] == "record"
    infos = [e for e in events if e["stage"] == "program_info"]
    assert infos[0]["data"]["version_actual"] == 0
    assert infos[0]["data"]["versiones"] == []
    assert infos[0]["data"]["total_credits"] == 0
    assert infos[0]["data"]["pensum_version"] == 5
    assert_matches_snapshot("programa_ausente.ndjson", response.text)


def test_version_fuera_de_lista(fake_portal: FakePortal):
    """La versión pedida no está en versiones de Cursum; se usa igual. Como no
    coincide con la del pensum oficial (v5), el total queda en creditosGrado."""
    fake_portal.add_cursum_pensum(7)
    response = _stream({**BODY, "pensum_version": 7})
    events = _events(response.text)
    assert events[-1]["stage"] == "record"
    infos = [e for e in events if e["stage"] == "program_info"]
    assert len(infos) == 1
    assert infos[0]["data"]["pensum_version"] == 7
    assert infos[0]["data"]["versiones"] == [3, 5]
    assert events[-1]["data"]["total_credits"] == 30
    assert_matches_snapshot("version_fuera_de_lista.ndjson", response.text)


def test_health():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_matches_snapshot("health.json", json_snapshot(response))
