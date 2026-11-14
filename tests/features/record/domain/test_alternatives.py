from app.features.record.domain.alternatives import (
    alternative_group,
    elective_credits,
    electives_done,
)

# 506 v5 real: mínimos de ayudame2, 168 - 128 obligatorias = 40 de electivas.
V5 = {"FIS": 3, "LAB": 1, "SOCIO": 9, "PRAC": 12, "EA": 15, "EB": 15, "EC": 15}
# 506 v3: tres líneas de 20 sin la palabra énfasis.
V3 = {"ALT": 4, "SOCIO": 8, "ALGO": 20, "ARQ": 20, "SOFT": 20}


def test_detecta_los_enfasis_por_cuadre_del_total():
    assert alternative_group(V5, 40) == frozenset({"EA", "EB", "EC"})
    assert alternative_group(V3, 32) == frozenset({"ALGO", "ARQ", "SOFT"})


def test_sin_exceso_no_hay_grupo():
    assert alternative_group({"A": 5, "B": 5}, 10) == frozenset()


def test_si_nada_cuadra_no_inventa_grupo():
    assert alternative_group(V5, 41) == frozenset()


def test_solo_cuenta_el_enfasis_con_mas_avance():
    passed = {"FIS": 3, "SOCIO": 12, "EA": 6, "EB": 3, "EC": 6}
    group = alternative_group(V5, 40)
    # 3 + 0 + 9 + 0 + max(6, 3, 6) = 18, no 3 + 9 + 15 = 27.
    assert elective_credits(V5, passed, group) == 18


def test_cumplidas_con_un_solo_enfasis_completo():
    group = alternative_group(V5, 40)
    done = {"FIS": 3, "LAB": 1, "SOCIO": 9, "PRAC": 12, "EB": 15}
    assert electives_done(V5, done, group) is True
    assert electives_done(V5, {**done, "PRAC": 0}, group) is False
