"""
ESTE ARCHIVO ES SOLO PARA EXPLORACIÓN MANUAL DE LAS PÁGINAS, NO PARA USO AUTOMÁTICO
Con este archivo puedes hacer tests manuales de forma local.
Se corre desde backend/: .venv/bin/python -m scripts.fetch_pages
"""

import getpass
import logging
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.errors import InvalidCredentials
from app.features.record.domain.grades import PassedSubject, merge_passed, passed_subject
from app.features.record.domain.record import build_record
from app.features.record.schemas import Subject
from app.features.record.service import merge_curriculum
from app.features.record.sources.gateway import PortalRecordSource
from app.portal.credentials import LoginPerRequest, PortalCredentials
from app.portal.session import PortalSession

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s — %(message)s")

_PROGRAMAS_URL = (
    "https://tsone.udea.edu.co/php_programas_estudiante/"
    "?app=listar"
    "&tipos=MAESTRIA,PREGRADO,DOCTORAD,ESPECIAL,PREPARAT,E-FLEXIB,SIGUEME,EXTENSIO"
    "&estados=ACTIVO,DESERTOR,CANCELO%20SEM,ADMITIDO,GRADUADO,TERMINOMATERIAS"
    "&canal=post&retorno=historia"
)

# Las páginas van a backend/pages/, no a scripts/pages/.
OUT = Path(__file__).resolve().parent.parent / "pages"
OUT.mkdir(exist_ok=True)

SEP = "─" * 60


def save(name: str, html: str) -> None:
    path = OUT / name
    path.write_text(html, encoding="utf-8")
    print(f"  Guardado: {path}")


def _attr(tag: Tag, name: str) -> str:
    """Atributo como texto: bs4 puede devolver listas para atributos multivaluados."""
    value = tag.get(name, "")
    if isinstance(value, list):
        return " ".join(value)
    return value or ""


def pause() -> None:
    input("\n  Presiona Enter para continuar...\n")


def show_constancia(source: PortalRecordSource) -> None:
    print()
    print("  — student_info() —")
    student = source.student_info()
    print(f"  Nombre    : {student.student_name!r}")
    print(f"  Programa  : {student.program_name!r}")
    print(f"  Código    : {student.program_code!r}")

    print()
    print("  — current_subjects() —")
    codes = [s.code for s in source.current_subjects()]
    print(f"  Códigos   : {codes}")


def show_historia(source: PortalRecordSource) -> dict[str, PassedSubject]:
    print()
    print("  — historia() —")
    program_code = source.student_info().program_code
    sem_codes = source.historia(program_code).semester_codes
    print(f"  Semestres encontrados: {len(sem_codes)}")
    for c in sem_codes:
        print(f"    {c}")

    print()
    print("  — semester_grades() + merge_passed() —")
    passed = merge_passed(
        [
            p
            for r in source.semester_grades(code)
            if (p := passed_subject(r.code, r.name, r.raw_grade))
        ]
        for code in sem_codes
    )
    print(f"  Total aprobadas: {len(passed)}")
    for code, subject in list(passed.items())[:10]:
        print(f"    {code:>10}  →  {subject.grade}")
    if len(passed) > 10:
        print(f"    … y {len(passed) - 10} más")
    return passed


def show_curriculum(source: PortalRecordSource, passed: dict[str, PassedSubject]) -> None:
    print()
    print("  — curriculum() —")
    student = source.student_info()
    program_code = student.program_code

    program = source.program(program_code)
    version_actual = (program.version_actual if program else None) or 0
    versiones = program.versiones if program else []
    total_credits = (program.total_credits if program else None) or 0
    print(
        f"  Versión actual: {version_actual}  |  Versiones: {versiones}  |  Créditos grado: {total_credits}"
    )

    pensum_v = int(
        input(f"  Versión del pensum a usar [{version_actual}]: ").strip() or version_actual
    )

    items = source.curriculum(program_code, pensum_v)
    current = {s.code for s in source.current_subjects()}
    subjects = merge_curriculum(items, passed, current)
    print(f"  Total materias: {len(subjects)}")

    record = build_record(
        student_name=student.student_name,
        program_name=student.program_name,
        program_code=program_code,
        pensum_version=pensum_v,
        version_actual=version_actual,
        versiones=versiones,
        total_credits=total_credits,
        subjects=subjects,
    )

    by_status: dict[str, list[Subject]] = {}
    for s in record.subjects:
        by_status.setdefault(s.status, []).append(s)
    for status, group in sorted(by_status.items()):
        print(
            f"    {status:<12} {len(group):>3} materias  |  {sum(s.credits for s in group)} créditos"
        )

    print()
    print("  Primeras 10 materias:")
    for s in record.subjects[:10]:
        print(f"    [{s.code}] {s.name[:38]:<38}  sem={s.semester}  cr={s.credits}  {s.status}")

    print()
    print("  — AcademicRecord —")
    avance = record.completed_credits / record.total_credits * 100 if record.total_credits else 0
    print(f"  Créditos totales : {record.total_credits}")
    print(f"  Créditos aprob.  : {record.completed_credits}  ({avance:.1f}%)")
    print(f"  Créditos en curso: {record.in_progress_credits}")

    out = OUT / "3_record.json"
    out.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    print(f"  Record guardado  : {out}")


def main() -> None:
    print("\n" + "═" * 60)
    print("  FETCH PAGES — Exploración página por página")
    print("═" * 60)

    username = input("\n  Usuario: ").strip()
    password = getpass.getpass("  Contraseña: ")

    provider = LoginPerRequest()
    print("\n  Autenticando…")
    try:
        session = provider.open(PortalCredentials(username, SecretStr(password)))
    except InvalidCredentials:
        print("  ✗ Login fallido.")
        sys.exit(1)
    print("  ✓ Sesión establecida.\n")
    try:
        explore(session)
    finally:
        provider.release(session)


def explore(session: PortalSession) -> None:
    source = PortalRecordSource(session)

    # Página 1 — constancia
    print(SEP)
    settings = get_settings()
    info_url = settings.tsone_url + "/php_constancia_estudiante/"
    historia_url = settings.tsone_url + "/php_historia_estudiante/"
    print(f"  [1] URL: {info_url}?app=consultar")
    resp = session.tsone_get(info_url + "?app=consultar")
    print(f"  Status: {resp.status_code}  |  Final URL: {resp.url}")
    save("1_constancia.html", resp.text)
    show_constancia(source)
    pause()

    # Página 2 — historia
    print(SEP)
    print(f"  [2] URL: {historia_url}?app=consultar")
    resp = session.tsone_get(historia_url + "?app=consultar")
    print(f"  Status: {resp.status_code}  |  Final URL: {resp.url}")
    save("2_historia.html", resp.text)
    passed = show_historia(source)
    pause()

    # Paso 3 — currículo (múltiples requests)
    print(SEP)
    print("  [3] currículo — CURSUM + semestres")
    show_curriculum(source, passed)
    pause()

    # Paso 4 — simulación del selector de programas
    print(SEP)
    print("  [4] Simulación selector de programas")
    print(f"  URL: {_PROGRAMAS_URL}")
    resp = session.tsone_get(_PROGRAMAS_URL)
    print(f"  Status: {resp.status_code}  |  Final URL: {resp.url}")
    save("4_programas.html", resp.text)

    soup = BeautifulSoup(resp.text, "lxml")
    print()
    print("  — Formulario encontrado —")
    form = soup.find("form")
    if not form:
        print("  ATENCIÓN: no se encontró ningún <form> en la página")
    else:
        print(f"  action : {form.get('action')!r}")
        print(f"  method : {form.get('method')!r}")

        selects = form.find_all("select")
        radios = form.find_all("input", {"type": "radio"})
        hiddens = form.find_all("input", {"type": "hidden"})

        print(f"  <select> encontrados : {len(selects)}")
        for sel in selects:
            print(f"    name={sel.get('name')!r}")
            for opt in sel.find_all("option"):
                print(f"      value={opt.get('value')!r}  texto={opt.get_text(strip=True)!r}")

        print(f"  <input type=radio> encontrados : {len(radios)}")
        for r in radios:
            print(f"      name={r.get('name')!r}  value={r.get('value')!r}")

        print(f"  <input type=hidden> encontrados: {len(hiddens)}")
        for h in hiddens:
            print(f"      name={h.get('name')!r}  value={h.get('value')!r}")

    print()
    print("  — Simulando PortalRecordSource.historia() con este response —")
    program_code = source.student_info().program_code
    print(f"  program_code a seleccionar: {program_code!r}")

    if form:
        option = soup.find("option", {"value": program_code})
        if not option:
            print(f"  ATENCIÓN: programa {program_code!r} no encontrado en el selector")
        else:
            form2 = soup.find("form", {"id": "form2"})
            action = (_attr(form2, "action") if form2 else "") or resp.url
            form_data = {
                "facultad": _attr(option, "data-facultad"),
                "nombre_facultad": _attr(option, "data-nombre-facultad"),
                "programa": program_code,
                "nombre_programa": option.get_text(strip=True),
                "maximo_semestre": _attr(option, "data-maximo-semestre"),
                "version": _attr(option, "data-version"),
                "estado": _attr(option, "data-estado"),
                "tipo": _attr(option, "data-tipo"),
                "mas_programas": "",
                "api": "programasudea",
            }
            print(f"  Datos del POST a form2: {form_data}")
            post_resp = session.tsone_post(action, form_data)
            print(f"  POST status={post_resp.status_code}  url={post_resp.url}")
            save("4b_post_form2.html", post_resp.text)

            print("  GET historia después de la selección…")
            hist_resp = session.tsone_get(historia_url + "?app=consultar")
            print(f"  GET status={hist_resp.status_code}  url={hist_resp.url}")
            result_soup = BeautifulSoup(hist_resp.text, "lxml")
            semestres = result_soup.find_all(None, {"data-semestre": True})
            print(f"  data-semestre encontrados: {len(semestres)}")
            for el in semestres:
                print(f"    {el.get('data-semestre')}")
            save("4c_historia_tras_seleccion.html", hist_resp.text)

    pause()

    print(SEP)
    print("  Archivos guardados en:", OUT)


if __name__ == "__main__":
    main()
