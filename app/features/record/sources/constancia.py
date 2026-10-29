"""Parsers puros de la constancia de matrícula (tsone, app=consultar)."""

import logging
import re

from bs4 import BeautifulSoup, Tag

from app.features.record.sources.models import EnrolledSubject, StudentInfo

log = logging.getLogger(__name__)


def parse_student_info(html: str) -> StudentInfo:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    name_m = re.search(r"Estudiante\s*[:\-]?\s*(.+)", text)
    prog_m = re.search(r"Programa\s*[:\-]?\s*\[(\d+)\]\s+(.+)", text)
    student_name = name_m.group(1).strip().lstrip(":").strip() if name_m else ""
    program_code = prog_m.group(1).strip() if prog_m else ""
    program_name = prog_m.group(2).strip() if prog_m else ""
    log.info(
        "parse_student_info: has_name=%s has_program=%s program_code=%s",
        bool(student_name),
        bool(program_code),
        program_code,
    )
    return StudentInfo(
        student_name=student_name, program_name=program_name, program_code=program_code
    )


def parse_current_subjects(html: str) -> list[EnrolledSubject]:
    soup = BeautifulSoup(html, "lxml")
    h5 = soup.find("h5", string=re.compile(r"MATERIAS MATRICULADAS", re.IGNORECASE))
    if not isinstance(h5, Tag):
        log.warning("parse_current_subjects: no se encontró h5 'MATERIAS MATRICULADAS'")
        return []
    subjects: list[EnrolledSubject] = []
    for div in h5.find_all_next("div", class_="alert-success"):
        # El nombre es lo que sigue al código en la misma línea.
        code_m = re.search(r"CÓDIGO\s*[:\-]?\s*(\d+)[ \t]*([^\n]*)", div.get_text(), re.IGNORECASE)
        if code_m:
            name = code_m.group(2).strip() or None
            subjects.append(EnrolledSubject(code=code_m.group(1), name=name))
    log.info(
        "parse_current_subjects: %d materias en curso, %d sin nombre",
        len(subjects),
        sum(1 for s in subjects if s.name is None),
    )
    return subjects
