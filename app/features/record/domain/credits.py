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

    El total siempre es creditosGrado del catálogo Cursum. Sumar obligatorias +
    mínimos lo infla (220 en vez de 168 en 506 v3) porque los énfasis son
    alternativos. Los mínimos se devuelven solo si son de la versión efectiva.
    """
    oblig = sum(s.credits for s in subjects if s.obligatoria)

    if bank_minimums and official_version == effective_version:
        log.info(
            "resolve_total_credits: versión=%d oblig=%d electivas_min=%d total=%d (cursum)",
            effective_version,
            oblig,
            sum(bank_minimums.values()),
            catalog_total,
        )
        return catalog_total, dict(bank_minimums)

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
