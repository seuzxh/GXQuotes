"""Skill ``plate-list`` 子命令单元测试（无网络）。"""

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).parents[1] / "skill" / "scripts" / "quotes.py"
_SPEC = importlib.util.spec_from_file_location("gxquotes_skill_quotes", _SCRIPT_PATH)
quotes = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(quotes)


class _FakePlateFetcher:
    calls = []

    def __init__(self, strict=False):
        assert strict is True

    def get_all_plates(self, plate_type, limit=None, *,
                       sort_by="change_pct", direction="desc"):
        self.calls.append((plate_type, limit, sort_by, direction))
        row = {
            "code": f"{plate_type}-code",
            "name": plate_type,
            "market": 44,
        }
        row.update({field: None for field in quotes.PLATE_SORT_FIELDS})
        row[sort_by] = 1.234
        return [row]


@pytest.fixture(autouse=True)
def fake_fetcher(monkeypatch):
    _FakePlateFetcher.calls = []
    monkeypatch.setattr(quotes, "ConceptPlateFetcher", _FakePlateFetcher)


def test_default_is_bounded_concept_list(capsys):
    assert quotes.main(["plate-list"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakePlateFetcher.calls == [("concept", 30, "change_pct", "desc")]
    assert payload["meta"]["count"] == 1
    assert payload["meta"]["market"] == 44
    assert payload["meta"]["type"] == "concept"
    assert payload["meta"]["subtype"] == 1
    assert payload["meta"]["full"] is False
    assert payload["meta"]["limit"] == 30
    assert payload["meta"]["sort"] == {"field": "change_pct", "direction": "desc"}
    assert payload["meta"]["retrieved_at"].endswith("Z")
    assert payload["data"][0]["code"] == "concept-code"
    assert payload["data"][0]["change_pct"] == 1.234
    assert set(quotes.PLATE_SORT_FIELDS).issubset(payload["data"][0])


def test_explicit_sort_and_direction_are_forwarded(capsys):
    assert quotes.main([
        "plate-list", "--type", "industry", "--sort", "amount",
        "--direction", "asc", "--limit", "5",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakePlateFetcher.calls == [("industry", 5, "amount", "asc")]
    assert payload["meta"]["sort"] == {"field": "amount", "direction": "asc"}
    assert payload["data"][0]["amount"] == 1.234
    assert "sort_value" not in payload["data"][0]


def test_all_types_use_stable_order_and_per_type_limit(capsys):
    assert quotes.main(["plate-list", "--type", "all", "--limit", "2"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakePlateFetcher.calls == [
        ("industry", 2, "change_pct", "desc"),
        ("concept", 2, "change_pct", "desc"),
        ("region", 2, "change_pct", "desc"),
        ("style", 2, "change_pct", "desc"),
    ]
    assert payload["meta"]["limit_per_type"] == 2
    assert payload["meta"]["counts"] == {
        "industry": 1,
        "concept": 1,
        "region": 1,
        "style": 1,
    }
    assert [row["type"] for row in payload["data"]] == [
        "industry",
        "concept",
        "region",
        "style",
    ]


def test_full_disables_limit(capsys):
    assert quotes.main(["plate-list", "--type", "region", "--full"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakePlateFetcher.calls == [("region", None, "change_pct", "desc")]
    assert payload["meta"]["full"] is True
    assert "limit" not in payload["meta"]


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_limit_must_be_positive(value):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["plate-list", "--limit", value])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("sort_by", ["906", "lead_stock", "unknown"])
def test_invalid_sort_is_rejected_by_argparse(sort_by):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["plate-list", "--sort", sort_by])
    assert exc_info.value.code == 2
