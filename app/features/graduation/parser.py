"""Parser de "MATERIAS FALTANTES PARA GRADO" (ayudame2, php_materias_faltantes_estudiante)."""

import re

from bs4 import BeautifulSoup, Tag

from app.features.graduation.schemas import (
    MissingBank,
    MissingForGraduation,
    MissingSubject,
    PendingGrade,
)

_TITLE = "MATERIAS FALTANTES PARA GRADO"
_SUBJECT = re.compile(r"código:\s*(\d+),\s*créditos:\s*(\d+)")
_PENDING = re.compile(r"código:\s*(\d+),\s*semestre:\s*(\d+)")
_COUNTS = r"{} que debes ver:\s*(\d+),\s*tienes aprobad[oa]s:\s*(\d+),\s*te falta cursar:\s*(\d+)"
_CREDITS = re.compile(_COUNTS.format("Créditos"))
_SUBJECTS = re.compile(_COUNTS.format("Materias"))


def parse_missing(html: str) -> MissingForGraduation | None:
    soup = BeautifulSoup(html, "lxml")
    if _TITLE not in soup.get_text(" ", strip=True):
        return None
    mandatory: list[MissingSubject] = []
    pending: list[PendingGrade] = []
    for heading in soup.find_all("h6"):
        title = heading.get_text(" ", strip=True)
        items = _list_after(heading)
        if title.startswith("MATERIAS OBLIGATORIAS"):
            mandatory = [s for li in items if (s := _subject(li)) is not None]
        elif title.startswith("MATERIAS OPCIONALES"):
            pending = [p for li in items if (p := _pending(li)) is not None]
    banks = [b for div in soup.select("div.alert") if (b := _bank(div)) is not None]
    return MissingForGraduation(mandatory=mandatory, banks=banks, pending=pending)


def _list_after(heading: Tag) -> list[Tag]:
    ul = heading.find_next_sibling()
    return ul.find_all("li") if isinstance(ul, Tag) and ul.name == "ul" else []


def _name(li: Tag) -> str:
    strong = li.find("strong")
    return strong.get_text(" ", strip=True) if isinstance(strong, Tag) else ""


def _subject(li: Tag) -> MissingSubject | None:
    m = _SUBJECT.search(li.get_text(" ", strip=True))
    if m is None:
        return None
    return MissingSubject(code=m.group(1), name=_name(li), credits=int(m.group(2)))


def _pending(li: Tag) -> PendingGrade | None:
    m = _PENDING.search(li.get_text(" ", strip=True))
    if m is None:
        return None
    return PendingGrade(code=m.group(1), name=_name(li), semester=m.group(2))


def _bank(div: Tag) -> MissingBank | None:
    heading = div.find("h6")
    if not isinstance(heading, Tag):
        return None
    name = heading.get_text(" ", strip=True).removeprefix("BANCO:").strip()
    text = div.get_text(" ", strip=True)
    credits = _CREDITS.search(text)
    if credits is None:
        return None
    subjects = _SUBJECTS.search(text)
    sub = [int(g) for g in subjects.groups()] if subjects else [None, None, None]
    return MissingBank(
        name=name,
        credits_required=int(credits.group(1)),
        credits_approved=int(credits.group(2)),
        credits_missing=int(credits.group(3)),
        subjects_required=sub[0],
        subjects_approved=sub[1],
        subjects_missing=sub[2],
        options=[s for li in div.find_all("li") if (s := _subject(li)) is not None],
    )
