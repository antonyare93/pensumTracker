from fastapi.testclient import TestClient

from main import app

ESPERADOS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def test_health_lleva_headers_de_seguridad():
    with TestClient(app) as client:
        headers = client.get("/api/health").headers
    for nombre, valor in ESPERADOS.items():
        assert headers[nombre] == valor


def test_respuestas_de_api_no_se_cachean():
    with TestClient(app) as client:
        headers = client.get("/api/health").headers
    assert headers["cache-control"] == "no-store"


def test_errores_tambien_llevan_headers():
    with TestClient(app) as client:
        headers = client.get("/no-existe").headers
    assert headers["x-content-type-options"] == "nosniff"


def test_stream_conserva_su_cache_control():
    with TestClient(app) as client:
        response = client.post("/api/login/stream", json={})
    assert response.headers["x-frame-options"] == "DENY"


def test_preflight_cors_lleva_headers():
    with TestClient(app) as client:
        headers = client.options(
            "/api/login/stream",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
        ).headers
    assert headers["x-content-type-options"] == "nosniff"
