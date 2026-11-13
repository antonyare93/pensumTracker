"""Homologación por nombre entre versiones del pensum."""

import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Final

from app.features.record.domain.grades import PassedSubject

log = logging.getLogger(__name__)

# Palabras que el pensum agrega o quita entre versiones sin que cambie la
# materia ("CONTROL ESTADÍSTICO DE (LA) CALIDAD").
FILLER_WORDS: Final = frozenset(
    {
        "DE",
        "DEL",
        "LA",
        "EL",
        "LOS",
        "LAS",
        "UN",
        "UNA",
        "UNOS",
        "UNAS",
        "Y",
        "EN",
        "A",
        "AL",
        "PARA",
        "THE",
        "OF",
    }
)


def normalize_name(name: str) -> str:
    """Clave para comparar nombres de materia entre versiones: sin tildes, signos
    ni palabras de relleno. Conserva los romanos, que sí separan materias."""
    nfd = unicodedata.normalize("NFD", name.upper())
    ascii_name = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    words = re.sub(r"[^A-Z0-9]+", " ", ascii_name).split()
    return " ".join(w for w in words if w not in FILLER_WORDS)


# Materias que el pensum renombró entre versiones y no coinciden por nombre.
# Solo se consultan si el nombre exacto no está en el pensum vigente.
NAME_EQUIVALENTS: Final[tuple[tuple[str, ...], ...]] = (
    ("LECTOESCRITURA", "ESPAÑOL ACADÉMICO"),
    ("INGLÉS I", "ENGLISH 1"),
    ("INGLÉS II", "ENGLISH 2"),
    ("INGLÉS III", "ENGLISH 3"),
    ("INGLÉS IV", "ENGLISH 4"),
    ("INGLÉS V", "ENGLISH 5"),
    ("FORMACIÓN CIUDADANA Y CONSTITUCIONAL", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
)


def _build_aliases(groups: tuple[tuple[str, ...], ...]) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    for group in groups:
        keys = [normalize_name(n) for n in group]
        for i, key in enumerate(keys):
            aliases[key] = tuple(k for j, k in enumerate(keys) if j != i)
    return aliases


NAME_ALIASES: Final = _build_aliases(NAME_EQUIVALENTS)


def homologate(
    passed: Mapping[str, PassedSubject], catalog: Mapping[str, str]
) -> dict[str, float | None]:
    """Código nuevo → nota para las materias aprobadas con otro código.

    `catalog` es código → nombre del plan vigente, en el orden de Cursum.
    Primero coincidencia directa por nombre normalizado, luego alias; la
    primera materia vieja que llega a un código nuevo se queda con él.
    """
    name_to_code = {normalize_name(name): code for code, name in catalog.items()}
    homologation: dict[str, float | None] = {}
    for old_code, subject in passed.items():
        if old_code in catalog:
            continue
        normalized = normalize_name(subject.name)
        if not normalized:
            continue
        new_code = name_to_code.get(normalized)
        if new_code is None:
            # Sin coincidencia directa: probamos los renombres conocidos.
            for alias in NAME_ALIASES.get(normalized, ()):
                new_code = name_to_code.get(alias)
                if new_code:
                    break
        if new_code and new_code not in homologation:
            log.info("fetch_curriculum: homologación %s→%s (%s)", old_code, new_code, subject.name)
            homologation[new_code] = subject.grade
    return homologation


def restore_full_names(
    passed: Mapping[str, PassedSubject], catalogs: Iterable[Mapping[str, str]]
) -> dict[str, PassedSubject]:
    """Cambia el nombre que la historia corta a 25 caracteres por el del catálogo.

    "FORMACIÓN CIUDAD Y CONSTI" no se parece a ningún nombre de otra versión;
    con el nombre completo del catálogo donde está su código sí se homologa.
    `catalogs` son código → nombre de otras versiones; gana el primero que tenga
    el código."""
    full: dict[str, str] = {}
    for catalog in catalogs:
        for code, name in catalog.items():
            full.setdefault(code, name)
    return {
        code: replace(subject, name=full[code]) if code in full else subject
        for code, subject in passed.items()
    }
