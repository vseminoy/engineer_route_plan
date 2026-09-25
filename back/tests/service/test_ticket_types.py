import csv
from pathlib import Path

import pytest

from src.domain import Skill
from src.service.ticket_types import Classification, TicketTypes

BACK_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BACK_DIR.parent / "docs"
SENTINELS = {"Адрес Офиса", "Адрес офиса"}


@pytest.fixture(scope="module")
def types() -> TicketTypes:
    return TicketTypes.from_file(BACK_DIR / "data" / "ticket_types.toml")


@pytest.mark.parametrize("bk", ["Глобальная проблема", "Подключение", "Локальная заявка", None])
def test_emergency_by_hd_whatever_bk(types: TicketTypes, bk: str | None) -> None:
    assert types.classify(bk, "Авария") == Classification(
        skill=Skill.EMERGENCY, priority=1, duration_min=80
    )


def test_global_problem_without_emergency(types: TicketTypes) -> None:
    assert types.classify("Глобальная проблема", "Информация") == Classification(
        skill=Skill.LOCAL_WORK, priority=3, duration_min=30
    )


def test_connection_and_reorder_priorities(types: TicketTypes) -> None:
    hd = "Заказ подключения/Дозаказ оборудования"
    assert types.classify("Подключение", hd) == Classification(
        skill=Skill.CONNECTION, priority=2, duration_min=70
    )
    assert types.classify("Дозаказ", hd) == Classification(
        skill=Skill.CONNECTION, priority=3, duration_min=20
    )


def test_tv_and_tve_are_separate_values(types: TicketTypes) -> None:
    for hd in ("ТВ. Замена приставки техником", "TVE/ENT. Замена приставки техником"):
        result = types.classify("Локальная заявка", hd)
        assert result is not None and result.skill == Skill.LOCAL_WORK


def test_every_source_type_mapped(types: TicketTypes) -> None:
    unmapped = set()
    for path in sorted(DOCS_DIR.glob("*/*.csv")):
        with path.open(encoding="cp1251", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                ticket = (row["Заявка"] or "").strip()
                if not ticket or ticket in SENTINELS:
                    continue
                bk, hd = row["Тип заявки BK"].strip(), row["Тип заявки HD"].strip()
                if types.classify(bk or None, hd) is None:
                    unmapped.add((bk, hd))
    assert unmapped == set()


def test_unknown_hd(types: TicketTypes) -> None:
    assert types.classify("Подключение", "Неизвестный тип") is None


CONFIG = """
[work_types.survey]
priority = 4
duration_min = 15

[bk]
"Обследование" = "survey"

[hd."Осмотр"]
skill = "local_work"

[statuses]
"Отправлена" = "sent"
"""


def test_config_from_file(tmp_path: Path) -> None:
    path = tmp_path / "types.toml"
    path.write_text(CONFIG, encoding="utf-8")
    assert TicketTypes.from_file(path).classify("Обследование", "Осмотр") == Classification(
        skill=Skill.LOCAL_WORK, priority=4, duration_min=15
    )


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ('skill = "local_work"', 'skill = "welding"', "skill"),
        ("priority = 4", "priority = 0", "priority"),
        ("duration_min = 15", "duration_min = 0", "duration_min"),
    ],
)
def test_config_invalid_rejected(tmp_path: Path, old: str, new: str, key: str) -> None:
    path = tmp_path / "types.toml"
    path.write_text(CONFIG.replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError, match=key):
        TicketTypes.from_file(path)
