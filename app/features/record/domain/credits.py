"""Total de créditos de grado según la versión efectiva del pensum."""

import logging
from collections.abc import Mapping, Sequence

from app.features.record.schemas import Subject

log = logging.getLogger(__name__)


def resolve_total_credits(
    catalog_total: int,
    subjects: Sequence[Subject],
    official_version: int | None,
    bank_minimums: Mapping[str, int],
    effective_version: int,
) -> tuple[int, dict[str, int]]:
    """Total de grado acorde a la versión del pensum efectiva.

    El total es creditosGrado del catálogo Cursum. Los mínimos por banco del
    pensum oficial (misma versión) solo se devuelven para los bancos: sumarlos a
    las obligatorias no da el plan (506 v3: 145 + 75 = 220, el plan es 168).
    Solo si Cursum no trae total se usa esa suma.
    """
    oblig = sum(s.credits for s in subjects if s.obligatoria)

    if bank_minimums and official_version == effective_version:
        total = catalog_total or oblig + sum(bank_minimums.values())
        log.info(
            "resolve_total_credits: versión=%d oblig=%d electivas_min=%d -> %d "
            "(catálogo cursum=%d)",
            effective_version,
            oblig,
            sum(bank_minimums.values()),
            total,
            catalog_total,
        )
        return total, dict(bank_minimums)

    log.info(
        "resolve_total_credits: fallback cursum=%d causa=%s | page_version=%s efectiva=%d "
        "bancos=%d",
        catalog_total,
        _fallback_cause(official_version, bank_minimums),
        official_version,
        effective_version,
        len(bank_minimums),
    )
    return catalog_total, {}


def _fallback_cause(official_version: int | None, bank_minimums: Mapping[str, int]) -> str:
    """Por qué no se usaron los mínimos oficiales. Solo describe el plan, no al estudiante."""
    if not bank_minimums:
        return "sin_pagina" if official_version is None else "sin_minimos"
    return "version_distinta"
