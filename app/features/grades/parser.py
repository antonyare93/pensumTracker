"""Parser de "MIS NOTAS DEL SEMESTRE" (tsone, php_notas_estudiante)."""

import re

from bs4 import BeautifulSoup, Tag

from app.features.grades.schemas import CourseGrades, Evaluation

_HEADER = re.compile(r"\[(\d+)\]\s*(.+)")
_ORDINAL = re.compile(r"^\d+\)\s*")
_SURVEY_PENDING = "debes evaluar"
_MAX_GRADE = 5.0


def parse_current_grades(html: str) -> list[CourseGrades]:
    soup = BeautifulSoup(html, "lxml")
    courses: list[CourseGrades] = []
    for header in soup.select("div.card-header"):
        match = _HEADER.search(header.get_text(" ", strip=True))
        body = header.find_next_sibling("div", class_="card-body")
        if match is None or not isinstance(body, Tag):
            continue
        courses.append(_course(match.group(1), match.group(2).strip(), body))
    return courses


def _course(code: str, name: str, body: Tag) -> CourseGrades:
    evaluations: list[Evaluation] = []
    pending = False
    for row in body.select("tbody tr"):
        cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        if len(cells) < 3:
            continue
        label, percent, grade = cells[0], _number(cells[1]), cells[2]
        if percent is None:
            continue
        pending = pending or grade.lower() == _SURVEY_PENDING
        evaluations.append(
            Evaluation(name=_ORDINAL.sub("", label), percent=percent, grade=_grade(grade))
        )
    return CourseGrades(code=code, name=name, evaluations=evaluations, survey_pending=pending)


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", ".").rstrip("%").strip())
    except ValueError:
        return None


def _grade(text: str) -> float | None:
    value = _number(text)
    if value is None or not 0 <= value <= _MAX_GRADE:
        return None
    return value
