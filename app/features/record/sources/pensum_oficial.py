"""Parser puro del pensum oficial (ayudame2): versión del plan y mínimos por banco."""

import logging
import re

from bs4 import BeautifulSoup

from app.features.record.sources.models import OfficialPensum

log = logging.getLogger(__name__)


def parse_official_pensum(html: str) -> OfficialPensum | None:
    if "PÉNSUM DEL PROGRAMA" not in html:
        return None
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    version: int | None = None
    version_m = re.search(
        r"Programa\s*:\s*\[[^\]]+\].*?\(v\s*(\d+)\)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if version_m:
        version = int(version_m.group(1))

    requirements: dict[str, int] = {}
    # Bloques: "NOMBRE BANCO (N materias)" + "Debes cursar al menos X créditos"
    for m in re.finditer(
        r"([A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9 ,./()+-]*?)\s*\(\d+\s+materias\)\s*"
        r"Debes cursar al menos\s+(\d+)\s+cr[eé]ditos",
        text,
        re.IGNORECASE,
    ):
        name = " ".join(m.group(1).split())
        requirements[name] = int(m.group(2))

    log.info(
        "parse_official_pensum: version=%s bancos=%s total_electivas=%d",
        version,
        requirements,
        sum(requirements.values()),
    )
    return OfficialPensum(version=version, bank_minimums=requirements)
