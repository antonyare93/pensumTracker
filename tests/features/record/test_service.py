"""Tests del armado del expediente: merge_curriculum y la etapa record.

Los casos de homologación usan datos del catálogo real de cursum (programa 504,
Ingeniería de Sistemas): la v3 trae 2517350 "FORMACIÓN CIUDADANA Y
CONSTITUCIONAL" y la v5 la renombró a 2517450 "CÁTEDRA DE FORMACIÓN CIUDADANA
Y CONSTITUCIONAL". Las pruebas de la etapa corren contra el portal falso.
"""

from collections.abc import Callable, Iterator

import pytest
from pydantic import SecretStr

from app.core.stream import StreamContext
from app.features.record.domain.grades import PassedSubject
from app.features.record.schemas import AcademicRecord, Subject
from app.features.record.service import RecordStage, enrolled_outside_pensum, merge_curriculum
from app.features.record.sources.cursum import parse_curriculum
from app.features.record.sources.gateway import PortalRecordSource, RecordSource
from app.features.record.sources.models import CursumSubject, EnrolledSubject
from app.portal.credentials import LoginPerRequest, PortalCredentials
from app.portal.session import PortalSession
from tests.fakes.portal import FakePortal


def _item(code: str, name: str, credits: int = 1, nivel: int = 1) -> dict[str, object]:
    return {
        "materia": code,
        "nombreMateria": name,
        "creditos": credits,
        "nivel": nivel,
        "tipoMateria": "OBLIGATORIA",
        "nombreBancoElectiva": " ",
        "requisitos": [],
    }


def _pensum(*items: dict[str, object]) -> list[CursumSubject]:
    return parse_curriculum(list(items))


def _passed(*subjects: PassedSubject) -> dict[str, PassedSubject]:
    return {p.code: p for p in subjects}


def _por_codigo(subjects: list[Subject]) -> dict[str, Subject]:
    return {s.code: s for s in subjects}


PENSUM_V5 = _pensum(
    _item("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
    _item("2508101", "PROGRAMACIÓN I", credits=3),
)


def test_catedra_renombrada_se_homologa():
    """El caso reportado: cursó 2517350, el pensum vigente trae 2517450."""
    passed = _passed(PassedSubject("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL", None))
    materias = _por_codigo(merge_curriculum(PENSUM_V5, passed, ()))
    assert materias["2517450"].cursada is True


def test_catedra_homologa_en_los_dos_sentidos():
    """Quien cursó la CÁTEDRA y pasó a un pensum con el nombre corto."""
    pensum_v73 = _pensum(_item("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL", credits=0))
    passed = _passed(
        PassedSubject("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL", 4.2)
    )
    materias = _por_codigo(merge_curriculum(pensum_v73, passed, ()))
    assert materias["2517350"].cursada is True
    assert materias["2517350"].nota == 4.2


def test_alias_no_desplaza_a_la_coincidencia_directa():
    """La v4 de varios programas trae las dos formas como materias separadas:
    el nombre exacto manda y el alias no debe robarle la homologación."""
    pensum_v4 = _pensum(
        _item("2517362", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
        _item("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
    )
    passed = _passed(PassedSubject("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL", None))
    materias = _por_codigo(merge_curriculum(pensum_v4, passed, ()))
    assert materias["2517362"].cursada is True
    assert materias["2517450"].cursada is False


def test_ingles_sigue_homologando():
    passed = _passed(PassedSubject("2517103", "INGLÉS III", 3.8))
    materias = merge_curriculum(_pensum(_item("2599999", "ENGLISH 3")), passed, ())
    assert _por_codigo(materias)["2599999"].cursada is True


def test_codigo_identico_no_pasa_por_el_nombre():
    passed = _passed(
        PassedSubject("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL", 4.0)
    )
    materias = _por_codigo(merge_curriculum(PENSUM_V5, passed, ()))
    assert materias["2517450"].cursada is True
    assert materias["2517450"].nota == 4.0


def test_materia_ajena_no_se_homologa():
    passed = _passed(PassedSubject("2504520", "COMPORTAMIENTO QUÍMICO DE LOS MATERIALES", 4.0))
    assert all(not m.cursada for m in merge_curriculum(PENSUM_V5, passed, ()))


def test_cursando_marca_las_materias_matriculadas():
    materias = _por_codigo(merge_curriculum(PENSUM_V5, {}, {"2508101"}))
    assert materias["2508101"].cursando is True
    assert materias["2508101"].cursada is False
    assert materias["2517450"].cursando is False


def test_matriculadas_fuera_del_pensum_se_devuelven_aparte():
    current = [
        EnrolledSubject(code="2508101", name="PROGRAMACIÓN I"),
        EnrolledSubject(code="3001234", name="CURSO DE OTRO PROGRAMA"),
        EnrolledSubject(code="3009999", name=None),
    ]
    outside = enrolled_outside_pensum(current, PENSUM_V5)
    assert [(s.code, s.name) for s in outside] == [
        ("3001234", "CURSO DE OTRO PROGRAMA"),
        ("3009999", None),
    ]


def test_record_stage_manda_las_matriculadas_fuera_del_pensum(session: PortalSession):
    ctx = StreamContext(session, 0)
    list(RecordStage().run(ctx))
    record = ctx.results["record"]
    assert isinstance(record, AcademicRecord)
    # La única matriculada de la fixture (2000300) está en el pensum 506.
    assert record.enrolled_outside_pensum == []


def test_sin_materias_en_el_pensum_devuelve_lista_vacia():
    passed = _passed(PassedSubject("2508101", "PROGRAMACIÓN I", 4.0))
    assert merge_curriculum([], passed, {"2508101"}) == []


def test_nota_textual_toma_la_nota_homologada():
    """Aprobada con nota textual (grade=None) y además homologada con 4.0 desde
    otro código: la nota sale de la homologación, como hoy."""
    pensum = _pensum(
        _item("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
        _item("2517450", "CÁTEDRA DE FORMACIÓN CIUDADANA Y CONSTITUCIONAL"),
    )
    passed = _passed(
        PassedSubject("2517350", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL", None),
        PassedSubject("2517999", "FORMACIÓN CIUDADANA Y CONSTITUCIONAL", 4.0),
    )
    materias = _por_codigo(merge_curriculum(pensum, passed, ()))
    assert materias["2517350"].cursada is True
    assert materias["2517350"].nota == 4.0


@pytest.fixture
def session(fake_portal: FakePortal) -> Iterator[PortalSession]:
    opened = LoginPerRequest().open(PortalCredentials("usuario", SecretStr("clave")))
    yield opened
    opened.close()


def test_record_stage_emite_las_etapas_en_orden(session: PortalSession):
    ctx = StreamContext(session, 0)
    stages = [e["stage"] for e in RecordStage().run(ctx)]
    assert stages[:4] == ["student_info", "program_info", "pensum", "pensum"]
    assert stages[-1] == "record"
    assert set(stages[4:-1]) <= {"program_info"}
    assert isinstance(ctx.results["record"], AcademicRecord)


def test_una_sola_fuente_por_stream(session: PortalSession):
    created: list[PortalSession] = []

    def factory(s: PortalSession) -> RecordSource:
        created.append(s)
        return PortalRecordSource(s)

    list(RecordStage(source_factory=factory).run(StreamContext(session, 0)))
    assert created == [session]


def test_version_automatica_sin_selector_usa_el_pensum_oficial(session: PortalSession):
    events = list(RecordStage().run(StreamContext(session, 0)))
    program_info = next(e for e in events if e["stage"] == "program_info")
    data = program_info["data"]
    assert isinstance(data, dict)
    # pensum_oficial.html declara (v5) y el portal de un solo programa no tiene selector.
    assert data["enrolled_version"] == 5
    assert data["pensum_version"] == 5


def test_version_pedida_con_varios_programas_no_fija_la_matriculada(
    fake_portal_factory: Callable[..., FakePortal],
):
    # 3 es una de las versiones del fake (PENSUM_VERSIONES) y la que trae el
    # selector de programas de historia en el portal de varios programas.
    fake_portal_factory(multi_program=True)
    opened = LoginPerRequest().open(PortalCredentials("usuario", SecretStr("clave")))
    try:
        ctx = StreamContext(opened, 3)
        events = list(RecordStage().run(ctx))
    finally:
        opened.close()
    program_info = next(e for e in events if e["stage"] == "program_info")
    data = program_info["data"]
    assert isinstance(data, dict)
    assert data["enrolled_version"] is None
    record = ctx.results["record"]
    assert isinstance(record, AcademicRecord)
    assert record.enrolled_version is None


class _ConMatriculaExtra(PortalRecordSource):
    """Portal falso con una matriculada más, que no está en el pensum 506."""

    def current_subjects(self) -> list[EnrolledSubject]:
        return [*super().current_subjects(), EnrolledSubject(code="3001234", name="CURSO LIBRE")]


def test_record_stage_no_pierde_la_matriculada_fuera_del_pensum(session: PortalSession):
    ctx = StreamContext(session, 0)
    list(RecordStage(source_factory=_ConMatriculaExtra).run(ctx))
    record = ctx.results["record"]
    assert isinstance(record, AcademicRecord)
    assert [(s.code, s.name) for s in record.enrolled_outside_pensum] == [
        ("3001234", "CURSO LIBRE")
    ]
    assert [s.code for s in record.subjects if s.cursando] == ["2000300"]
