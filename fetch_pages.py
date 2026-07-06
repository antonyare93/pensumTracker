from services.academic_service import AcademicRecordBuilder
from scraper.portal_scraper import PortalScraper
import sys
import getpass
import logging
from pathlib import Path
from bs4 import BeautifulSoup

"""
ESTE ARCHIVO ES SOLO PARA EXPLORACIÓN MANUAL DE LAS PÁGINAS, NO PARA USO AUTOMÁTICO
Con este archivo puedes hacer tests manuales de forma local
"""

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s  %(name)s — %(message)s")

sys.path.insert(0, str(Path(__file__).parent))


_PROGRAMAS_URL = (
    "https://tsone.udea.edu.co/php_programas_estudiante/"
    "?app=listar"
    "&tipos=MAESTRIA,PREGRADO,DOCTORAD,ESPECIAL,PREPARAT,E-FLEXIB,SIGUEME,EXTENSIO"
    "&estados=ACTIVO,DESERTOR,CANCELO%20SEM,ADMITIDO,GRADUADO,TERMINOMATERIAS"
    "&canal=post&retorno=historia"
)

OUT = Path(__file__).parent / "pages"
OUT.mkdir(exist_ok=True)

SEP = "─" * 60


def save(name: str, html: str):
    path = OUT / name
    path.write_text(html, encoding="utf-8")
    print(f"  Guardado: {path}")


def pause():
    input("\n  Presiona Enter para continuar...\n")


def show_constancia(scraper: PortalScraper):
    print()
    print("  — fetch_student_info() —")
    student_name, program_name, program_code = scraper.fetch_student_info()
    print(f"  Nombre    : {student_name!r}")
    print(f"  Programa  : {program_name!r}")
    print(f"  Código    : {program_code!r}")

    print()
    print("  — fetch_current_subjects() —")
    codes = scraper.fetch_current_subjects()
    print(f"  Códigos   : {codes}")


def show_historia(scraper: PortalScraper):
    print()
    print("  — _fetch_semester_codes() —")
    _, _, program_code = scraper.fetch_student_info()
    sem_codes = scraper._fetch_semester_codes()
    print(f"  Semestres encontrados: {len(sem_codes)}")
    for c in sem_codes:
        print(f"    {c}")

    print()
    print("  — fetch_passed_subjects() —")
    passed = scraper.fetch_passed_subjects()
    print(f"  Total aprobadas: {len(passed)}")
    for code, grade in list(passed.items())[:10]:
        print(f"    {code:>10}  →  {grade}")
    if len(passed) > 10:
        print(f"    … y {len(passed) - 10} más")


def show_curriculum(scraper: PortalScraper):
    print()
    print("  — fetch_curriculum() —")
    _, _, program_code = scraper.fetch_student_info()

    version_actual, versiones, total_credits = scraper.fetch_program_info(
        program_code)
    print(
        f"  Versión actual: {version_actual}  |  Versiones: {versiones}  |  Créditos grado: {total_credits}")

    pensum_v = int(input(
        f"  Versión del pensum a usar [{version_actual}]: ").strip() or version_actual)
    scraper._pensum_version = pensum_v

    subjects = scraper.fetch_curriculum()
    print(f"  Total materias: {len(subjects)}")

    by_status: dict[str, list] = {}
    for s in subjects:
        by_status.setdefault(s.status, []).append(s)
    for status, group in sorted(by_status.items()):
        print(
            f"    {status:<12} {len(group):>3} materias  |  {sum(s.credits for s in group)} créditos")

    print()
    print("  Primeras 10 materias:")
    for s in subjects[:10]:
        print(
            f"    [{s.code}] {s.name[:38]:<38}  sem={s.semester}  cr={s.credits}  {s.status}")

    student_name, program_name, _ = scraper.fetch_student_info()
    record = AcademicRecordBuilder().build(
        student_name=student_name,
        program_name=program_name,
        program_code=program_code,
        pensum_version=scraper._pensum_version,
        version_actual=version_actual,
        versiones=versiones,
        total_credits=total_credits,
        subjects=subjects,
    )
    print()
    print("  — AcademicRecord —")
    avance = record.completed_credits / record.total_credits * \
        100 if record.total_credits else 0
    print(f"  Créditos totales : {record.total_credits}")
    print(f"  Créditos aprob.  : {record.completed_credits}  ({avance:.1f}%)")
    print(f"  Créditos en curso: {record.in_progress_credits}")

    out = OUT / "3_record.json"
    out.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    print(f"  Record guardado  : {out}")


def main():
    print("\n" + "═" * 60)
    print("  FETCH PAGES — Exploración página por página")
    print("═" * 60)

    username = input("\n  Usuario: ").strip()
    password = getpass.getpass("  Contraseña: ")

    scraper = PortalScraper(cookies={})
    print("\n  Autenticando…")
    if not scraper.login(username, password):
        print("  ✗ Login fallido.")
        sys.exit(1)
    print("  ✓ Sesión establecida.\n")

    # Página 1 — constancia
    print(SEP)
    print(f"  [1] URL: {scraper._INFO_URL}?app=consultar")
    resp = scraper._tsone_get(scraper._INFO_URL + "?app=consultar")
    print(f"  Status: {resp.status_code}  |  Final URL: {resp.url}")
    save("1_constancia.html", resp.text)
    show_constancia(scraper)
    pause()

    # Página 2 — historia
    print(SEP)
    _, _, program_code = scraper.fetch_student_info()
    print(f"  [2] URL: {scraper._HISTORIA_URL}?app=consultar")
    soup = scraper._fetch_historia_soup(program_code)
    save("2_historia.html", soup.prettify())
    show_historia(scraper)
    pause()

    # Paso 3 — currículo (múltiples requests)
    print(SEP)
    print("  [3] fetch_curriculum() — CURSUM + semestres")
    show_curriculum(scraper)
    pause()

    # Paso 4 — simulación del selector de programas
    print(SEP)
    print(f"  [4] Simulación selector de programas")
    print(f"  URL: {_PROGRAMAS_URL}")
    resp = scraper._tsone_get(_PROGRAMAS_URL)
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
                print(
                    f"      value={opt.get('value')!r}  texto={opt.get_text(strip=True)!r}")

        print(f"  <input type=radio> encontrados : {len(radios)}")
        for r in radios:
            print(f"      name={r.get('name')!r}  value={r.get('value')!r}")

        print(f"  <input type=hidden> encontrados: {len(hiddens)}")
        for h in hiddens:
            print(f"      name={h.get('name')!r}  value={h.get('value')!r}")

    print()
    print("  — Simulando _fetch_historia_soup() con este response —")
    _, _, program_code = scraper.fetch_student_info()
    print(f"  program_code a seleccionar: {program_code!r}")

    if form:
        option = soup.find("option", {"value": program_code})
        if not option:
            print(
                f"  ATENCIÓN: programa {program_code!r} no encontrado en el selector")
        else:
            form2 = soup.find("form", {"id": "form2"})
            action = (form2.get("action") if form2 else None) or resp.url
            form_data = {
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
            print(f"  Datos del POST a form2: {form_data}")
            post_resp = scraper._tsone_post(action, form_data)
            print(
                f"  POST status={post_resp.status_code}  url={post_resp.url}")
            save("4b_post_form2.html", post_resp.text)

            print(f"  GET historia después de la selección…")
            hist_resp = scraper._tsone_get(
                scraper._HISTORIA_URL + "?app=consultar")
            print(f"  GET status={hist_resp.status_code}  url={hist_resp.url}")
            result_soup = BeautifulSoup(hist_resp.text, "lxml")
            semestres = result_soup.find_all(attrs={"data-semestre": True})
            print(f"  data-semestre encontrados: {len(semestres)}")
            for el in semestres:
                print(f"    {el.get('data-semestre')}")
            save("4c_historia_tras_seleccion.html", hist_resp.text)

    pause()

    print(SEP)
    print("  Archivos guardados en:", OUT)


if __name__ == "__main__":
    main()
