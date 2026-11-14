import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.portal.session import PortalSession

if TYPE_CHECKING:
    from app.portal.credentials import PortalCredentials

log = logging.getLogger(__name__)


def _sso_url() -> str:
    return get_settings().ayudame2_url + "/php_mua_externos/"


def _historia_url() -> str:
    return get_settings().tsone_url + "/php_historia_estudiante/"


def reauth(session: PortalSession, host: str, password: str) -> str | None:
    relogin_base = f"https://{host}/php_relogin/"
    reauth_end = f"https://{host}/php_libs/reauthenticate_end.php"

    session.post(
        relogin_base + "?app=ingreso",
        data={"urlref": reauth_end},
        allow_redirects=True,
    )

    resp = session.post(
        relogin_base + "?app=validar",
        data={"clave": password},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*",
        },
    )
    try:
        data = resp.json()
    except Exception:
        return None

    if data.get("error") or "hash" not in data:
        # El mensaje del portal no lleva datos del estudiante; el hash nunca se registra.
        log.warning(
            "reauth %s: sin hash | claves=%s error=%r",
            host,
            sorted(data) if isinstance(data, dict) else type(data).__name__,
            data.get("error") if isinstance(data, dict) else None,
        )
        return None

    h = data["hash"]
    session.set_udeasecure(h)

    end_resp = session.get(f"{reauth_end}?hash={h}", allow_redirects=True)
    end_soup = BeautifulSoup(end_resp.text, "lxml")
    auto_form = end_soup.find("form")
    if auto_form:
        action = auto_form.get("action", "")
        if isinstance(action, str) and action:
            final_resp = session.post(action, data={}, allow_redirects=True)
            return final_resp.text
    return None


def validate(session: PortalSession) -> bool:
    resp = session.tsone_get(_historia_url() + "?app=consultar")
    invalid = (
        resp.status_code != 200
        or "php_relogin" in resp.url
        or "No hay usuario conectado" in resp.text
        or "php_relogin" in resp.text
    )
    return not invalid


def login(session: PortalSession, credentials: "PortalCredentials") -> bool:
    password = credentials.password.get_secret_value()
    log.info("login: SSO ayudame2")
    sso = session.post(
        _sso_url(),
        data={"usuario": credentials.username, "clave": password},
        allow_redirects=True,
    )
    log.info("login: SSO status=%d final_url=%s", sso.status_code, sso.url)
    if sso.status_code != 200:
        log.warning("login: SSO falló con status=%d", sso.status_code)
        return False
    session.cookies.set("user_name", credentials.username, domain=".udea.edu.co", path="/")

    session.get(_historia_url() + "?app=consultar", allow_redirects=True)
    settings = get_settings()
    tsone_host = urlsplit(settings.tsone_url).netloc
    ayudame2_host = urlsplit(settings.ayudame2_url).netloc

    log.info("login: reauth tsone")
    reauth(session, tsone_host, password)
    if not session.udeasecure:
        log.warning("login: reauth tsone falló, udeasecure vacío")
        return False
    log.info("login: reauth tsone ok | udeasecure presente=True")

    # El pensum oficial (mínimos por banco) vive en ayudame2.
    log.info("login: reauth ayudame2")
    reauth(session, ayudame2_host, password)

    valid = validate(session)
    log.info("login: validate_session=%s", valid)
    return valid
