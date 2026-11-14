"""Bancos alternativos (énfasis): el estudiante completa uno solo del grupo.

ayudame2 da el mínimo de cada banco, pero los énfasis son excluyentes: sumar los
tres no cuadra con el total del pensum. El grupo se detecta por ese cuadre, no por
el nombre, porque en v3 las líneas no dicen "énfasis".
"""

from collections import Counter
from collections.abc import Mapping

Group = frozenset[str]


def alternative_group(requirements: Mapping[str, int], electives_required: int) -> Group:
    """Bancos con el mismo mínimo que, contados una vez, hacen cuadrar las electivas."""
    excess = sum(requirements.values()) - electives_required
    if excess <= 0:
        return frozenset()
    for minimum, count in Counter(requirements.values()).items():
        if count >= 2 and minimum > 0 and (count - 1) * minimum == excess:
            return frozenset(name for name, req in requirements.items() if req == minimum)
    return frozenset()


def elective_credits(
    requirements: Mapping[str, int], passed: Mapping[str, int], group: Group
) -> int:
    """Créditos de electivas que cuentan: cada banco topado, del grupo solo el mejor."""
    single = sum(min(passed.get(n, 0), r) for n, r in requirements.items() if n not in group)
    best = max((min(passed.get(n, 0), requirements[n]) for n in group), default=0)
    return single + best


def electives_done(
    requirements: Mapping[str, int], passed: Mapping[str, int], group: Group
) -> bool:
    """Todos los bancos sueltos cumplidos y, si hay grupo, al menos uno de él."""
    singles = all(passed.get(n, 0) >= r for n, r in requirements.items() if n not in group)
    one_of_group = not group or any(passed.get(n, 0) >= requirements[n] for n in group)
    return singles and one_of_group
