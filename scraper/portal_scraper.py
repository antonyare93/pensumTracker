import ssl
import re
import logging
import unicodedata
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from bs4 import BeautifulSoup
from models.academic import Subject
from scraper.base import Authenticator, CurriculumFetcher, AcademicHistoryFetcher

log = logging.getLogger(__name__)

_PASSING_GRADE = 3.0

# Materias que el pensum renombró entre versiones y no coinciden por nombre.
# Claves y valores ya normalizados (sin tildes, mayúsculas).
_NAME_ALIASES: dict[str, str] = {
    "LECTOESCRITURA": "ESPANOL ACADEMICO",
    "INGLES I": "ENGLISH 1",
    "INGLES II": "ENGLISH 2",
    "INGLES III": "ENGLISH 3",
    "INGLES IV": "ENGLISH 4",
    "INGLES V": "ENGLISH 5",
    "ENGLISH 1": "INGLES I",
    "ENGLISH 2": "INGLES II",
    "ENGLISH 3": "INGLES III",
    "ENGLISH 4": "INGLES IV",
    "ENGLISH 5": "INGLES V",
}


class _LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


class PortalScraper(Authenticator, CurriculumFetcher, AcademicHistoryFetcher):
    _HISTORIA_URL = "https://tsone.udea.edu.co/php_historia_estudiante/"
    _INFO_URL = "https://tsone.udea.edu.co/php_constancia_estudiante/"
    _CURSUM_URL = "https://wsingenieria.udea.edu.co:8094/cursum/ingenieria/pensum"

    def __init__(self, cookies: dict[str, str], pensum_version: int = 0):
        self._session = requests.Session()
        self._session.mount("https://", _LegacyTLSAdapter())
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        })
        for name, value in cookies.items():
            if name in ("user_name", "udeasecure"):
                self._session.cookies.set(
                    name, value, domain=".udea.edu.co", path="/")
            elif name == "phpsessid_ayudame2":
                self._session.cookies.set(
                    "PHPSESSID", value, domain="ayudame2.udea.edu.co", path="/")
        self._pensum_version = pensum_version
        self._udeasecure = cookies.get("udeasecure", "")
        self._student_cache: tuple[str, str, str] | None = None
        self._info_cache: BeautifulSoup | None = None

    def _do_reauth(self, host: str, password: str) -> str | None:
        relogin_base = f"https://{host}/php_relogin/"
        reauth_end = f"https://{host}/php_libs/reauthenticate_end.php"

        self._session.post(
            relogin_base + "?app=ingreso",
            data={"urlref": reauth_end},
            allow_redirects=True,
        )

        resp = self._session.post(
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
            return None

        h = data["hash"]
        self._udeasecure = h
        self._session.cookies.set(
            "udeasecure", h, domain=".udea.edu.co", path="/")

        end_resp = self._session.get(
            f"{reauth_end}?hash={h}", allow_redirects=True)
        end_soup = BeautifulSoup(end_resp.text, "lxml")
        auto_form = end_soup.find("form")
        if auto_form:
            action = auto_form.get("action", "")
            if action:
                final_resp = self._session.post(
                    action, data={}, allow_redirects=True)
                return final_resp.text
        return None

    def login(self, username: str, password: str) -> bool:
        log.info("login: SSO ayudame2")
        sso = self._session.post(
            "https://ayudame2.udea.edu.co/php_mua_externos/",
            data={"usuario": username, "clave": password},
            allow_redirects=True,
        )
        log.info("login: SSO status=%d final_url=%s", sso.status_code, sso.url)
        if sso.status_code != 200:
            log.warning("login: SSO falló con status=%d", sso.status_code)
            return False
        self._session.cookies.set(
            "user_name", username, domain=".udea.edu.co", path="/")

        self._session.get(self._HISTORIA_URL +
                          "?app=consultar", allow_redirects=True)
        log.info("login: reauth tsone")
        self._do_reauth("tsone.udea.edu.co", password)
        if not self._udeasecure:
            log.warning("login: reauth tsone falló, udeasecure vacío")
            return False
        log.info("login: reauth tsone ok | udeasecure presente=True")

        resp = self._tsone_get(self._INFO_URL + "?app=consultar")
        self._info_cache = BeautifulSoup(resp.text, "lxml")
        log.info("login: constancia GET status=%d final_url=%s",
                 resp.status_code, resp.url)

        valid = self.validate_session()
        log.info("login: validate_session=%s", valid)
        return valid

    def logout(self) -> None:
        self._session.cookies.clear()
        self._udeasecure = ""
        self._student_cache = None
        self._info_cache = None

    def _tsone_get(self, url: str) -> requests.Response:
        if self._udeasecure:
            self._session.cookies.set(
                "udeasecure", self._udeasecure, domain=".udea.edu.co", path="/")
        return self._session.get(url, allow_redirects=True)

    def _tsone_post(self, url: str, data: dict) -> requests.Response:
        if self._udeasecure:
            self._session.cookies.set(
                "udeasecure", self._udeasecure, domain=".udea.edu.co", path="/")
        return self._session.post(url, data=data, allow_redirects=True)

    def _fetch_historia_soup(self, program_code: str) -> BeautifulSoup:
        resp = self._tsone_get(self._HISTORIA_URL + "?app=consultar")
        soup = BeautifulSoup(resp.text, "lxml")
        if "php_programas_estudiante" not in resp.url:
            return soup
        log.info(
            "_fetch_historia_soup: selector de programa detectado, seleccionando %s", program_code)
        option = soup.find("option", {"value": program_code})
        if not option:
            log.warning(
                "_fetch_historia_soup: programa %s no encontrado en el selector", program_code)
            return soup
        form2 = soup.find("form", {"id": "form2"})
        if not form2:
            log.warning("_fetch_historia_soup: form2 no encontrado")
            return soup
        action = form2.get("action") or resp.url
        form_data: dict[str, str] = {
            "facultad":        option.get("data-facultad", ""),
            "nombre_facultad": option.get("data-nombre-facultad", ""),
            "programa":        program_code,
            "nombre_programa": option.get_text(strip=True),
            "maximo_semestre": option.get("data-maximo-semestre", ""),
            "version":         option.get("data-version", ""),
            "estado":          option.get("data-estado", ""),
            "tipo":            option.get("data-tipo", ""),
            "mas_programas":   "",
            "api":             "programasudea",
        }
        self._tsone_post(action, form_data)
        hist_resp = self._tsone_get(self._HISTORIA_URL + "?app=consultar")
        return BeautifulSoup(hist_resp.text, "lxml")

    def _fetch_info_soup(self) -> BeautifulSoup:
        if self._info_cache is None:
            resp = self._tsone_get(self._INFO_URL + "?app=consultar")
            self._info_cache = BeautifulSoup(resp.text, "lxml")
        return self._info_cache

    def validate_session(self) -> bool:
        resp = self._tsone_get(self._HISTORIA_URL + "?app=consultar")
        invalid = (
            resp.status_code != 200
            or "php_relogin" in resp.url
            or "No hay usuario conectado" in resp.text
            or "php_relogin" in resp.text
        )
        return not invalid

    def _parse_grade(self, raw: str) -> float | None:
        raw = raw.strip()
        if raw.startswith("."):
            raw = "0" + raw
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        nfd = unicodedata.normalize("NFD", name.upper())
        ascii_name = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
        return " ".join(ascii_name.split())

    def _fetch_semester_grades(self, sem_code: str) -> dict[str, tuple[float, str]]:
        resp = self._tsone_get(self._HISTORIA_URL +
                               f"?app=ver_semestre&semestre={sem_code}")
        soup = BeautifulSoup(resp.text, "lxml")
        result: dict[str, tuple[float, str]] = {}
        for row in soup.select("table tr.text-center"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            raw = cells[0].get_text(strip=True)
            match = re.match(r"\[(\w+)\]\s*(.*)", raw)
            if not match:
                continue
            code = match.group(1)
            name = match.group(2).strip()
            grade = self._parse_grade(cells[2].get_text(strip=True))
            if grade is not None and grade >= _PASSING_GRADE:
                result[code] = (grade, name)
        return result

    def _fetch_semester_codes(self) -> list[str]:
        _, _, program_code = self.fetch_student_info()
        soup = self._fetch_historia_soup(program_code)
        codes = [el.get("data-semestre")
                 for el in soup.find_all(attrs={"data-semestre": True})]
        return [c for c in codes if c]

    def _fetch_passed_with_names(self) -> dict[str, tuple[float, str]]:
        sem_codes = self._fetch_semester_codes()
        log.info("_fetch_passed_with_names: %d semestres encontrados",
                 len(sem_codes))
        passed: dict[str, tuple[float, str]] = {}
        for sem_code in sem_codes:
            passed.update(self._fetch_semester_grades(sem_code))
        log.info("_fetch_passed_with_names: %d materias aprobadas", len(passed))
        return passed

    def fetch_passed_subjects(self) -> dict[str, float]:
        return {code: grade for code, (grade, _) in self._fetch_passed_with_names().items()}

    def fetch_student_info(self) -> tuple[str, str, str]:
        if self._student_cache:
            return self._student_cache
        soup = self._fetch_info_soup()
        text = soup.get_text(separator="\n")
        name_m = re.search(r"Estudiante\s*[:\-]?\s*(.+)", text)
        prog_m = re.search(r"Programa\s*[:\-]?\s*\[(\d+)\]\s+(.+)", text)
        student_name = name_m.group(1).strip().lstrip(":").strip() if name_m else ""
        program_code = prog_m.group(1).strip() if prog_m else ""
        program_name = prog_m.group(2).strip() if prog_m else ""
        log.info(
            "fetch_student_info: has_name=%s has_program=%s program_code=%s",
            bool(student_name), bool(program_code), program_code,
        )
        self._student_cache = (student_name, program_name, program_code)
        return self._student_cache

    def fetch_current_subjects(self) -> list[str]:
        soup = self._fetch_info_soup()
        h5 = soup.find("h5", string=re.compile(r"MATERIAS MATRICULADAS", re.IGNORECASE))
        if not h5:
            log.warning("fetch_current_subjects: no se encontró h5 'MATERIAS MATRICULADAS'")
            return []
        codes: list[str] = []
        for div in h5.find_all_next("div", class_="alert-success"):
            code_m = re.search(r"CÓDIGO\s*[:\-]?\s*(\d+)", div.get_text(), re.IGNORECASE)
            if code_m:
                codes.append(code_m.group(1))
        log.info("fetch_current_subjects: %d materias en curso", len(codes))
        return codes

    def fetch_program_info(self, program_code: str) -> tuple[int, list[int], int]:
        resp = self._session.get(
            "https://wsingenieria.udea.edu.co:8094/cursum/ingenieria/programas",
            allow_redirects=True,
        )
        for p in resp.json():
            if str(p["codigo"]) == program_code:
                version_actual = p.get("versionActual", 0)
                raw = p.get("versiones", "")
                versiones = [int(v)
                             for v in raw.split(",") if v.strip().isdigit()]
                total_credits = p.get("creditosGrado", 0)
                return version_actual, versiones, total_credits
        return 0, [], 0

    def fetch_curriculum(self) -> list[Subject]:
        _, _, program_code = self.fetch_student_info()
        passed_with_names = self._fetch_passed_with_names()
        passed = {code: grade for code,
                  (grade, _) in passed_with_names.items()}
        current = set(self.fetch_current_subjects())
        log.info("fetch_curriculum: cursando=%d | program_code=%s pensum_version=%d",
                 len(current), program_code, self._pensum_version)

        cursum_url = f"{self._CURSUM_URL}/{program_code}/{self._pensum_version}"
        resp = self._session.get(cursum_url, allow_redirects=True)
        log.info("fetch_curriculum: cursum status=%d url=%s",
                 resp.status_code, resp.url)
        cursum_items = resp.json()
        if not isinstance(cursum_items, list):
            log.error("fetch_curriculum: cursum no devolvió lista, tipo=%s contenido=%r",
                      type(cursum_items).__name__, str(cursum_items)[:200])
            return []
        log.info("fetch_curriculum: cursum devolvió %d materias",
                 len(cursum_items))

        cursum_codes = {str(item["materia"]) for item in cursum_items}
        name_to_code = {self._normalize_name(item["nombreMateria"]): str(
            item["materia"]) for item in cursum_items}
        homologation: dict[str, float] = {}
        for old_code, (grade, name) in passed_with_names.items():
            if old_code not in cursum_codes:
                normalized = self._normalize_name(name)
                canonical = _NAME_ALIASES.get(normalized, normalized)
                new_code = name_to_code.get(canonical)
                if new_code and new_code not in homologation:
                    log.info("fetch_curriculum: homologación %s→%s (%s)",
                             old_code, new_code, name)
                    homologation[new_code] = grade

        subjects: list[Subject] = []
        for item in cursum_items:
            code = str(item["materia"])
            reqs = item.get("requisitos", [])
            is_cursada = code in passed or code in homologation
            nota = passed.get(code) or homologation.get(code)
            subjects.append(Subject(
                code=code,
                name=item["nombreMateria"],
                credits=item["creditos"],
                semester=item["nivel"],
                obligatoria=item.get(
                    "tipoMateria", "OBLIGATORIA") == "OBLIGATORIA",
                elective_bank=item.get("nombreBancoElectiva", "").strip() or None,
                prerequisites=[str(r["materiaRequisito"])
                               for r in reqs if r["tipoRequisito"] == "PRERREQ"],
                corequisites=[str(r["materiaRequisito"])
                              for r in reqs if r["tipoRequisito"] == "CORREQ"],
                cursada=is_cursada,
                nota=nota,
                cursando=code in current,
            ))
        return subjects
