"""Skill ``members`` 子命令排序与限量单元测试（无网络）。"""

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).parents[1] / "skill" / "scripts" / "quotes.py"
_SPEC = importlib.util.spec_from_file_location("gxquotes_skill_members", _SCRIPT_PATH)
quotes = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(quotes)


class _FakeMemberFetcher:
    calls = []

    def __init__(self, strict=False):
        assert strict is True

    def get_concept_plate_stocks(self, plate, start=0, count=10, *,
                                 sort_by="change_pct", direction="desc"):
        self.calls.append(("page", plate, start, count, sort_by, direction))
        return [
            {"code": plate, "name": "板块自身", "market": 44},
            {
                "code": "600001",
                "name": "成份股一",
                "market": 1,
                sort_by: 1.234,
            },
            {
                "code": "000001",
                "name": "成份股二",
                "market": 0,
                sort_by: 0.123,
            },
        ]

    def iter_concept_plate_stocks(self, plate, page_size=100, *,
                                  sort_by="change_pct", direction="desc"):
        self.calls.append(("all", plate, page_size, sort_by, direction))
        yield {
            "code": "600001",
            "name": "成份股一",
            "market": 1,
            sort_by: 1.234,
        }


@pytest.fixture(autouse=True)
def fake_fetcher(monkeypatch):
    _FakeMemberFetcher.calls = []
    monkeypatch.setattr(quotes, "ConceptPlateFetcher", _FakeMemberFetcher)


def test_default_is_change_pct_desc_top_50(capsys):
    assert quotes.main(["members", "994612"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMemberFetcher.calls == [
        ("page", "994612", 0, 50, "change_pct", "desc"),
    ]
    assert payload["meta"]["count"] == 2
    assert payload["meta"]["plate"] == "994612"
    assert payload["meta"]["full"] is False
    assert payload["meta"]["limit"] == 50
    assert payload["meta"]["sort"] == {
        "field": "change_pct",
        "direction": "desc",
    }
    assert payload["meta"]["retrieved_at"].endswith("Z")
    assert all(str(row["market"]) != "44" for row in payload["data"])


def test_custom_sort_direction_and_limit_are_forwarded(capsys):
    assert quotes.main([
        "members", "991342", "--sort", "amount",
        "--direction", "asc", "--limit", "1",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMemberFetcher.calls == [
        ("page", "991342", 0, 1, "amount", "asc"),
    ]
    assert payload["meta"]["limit"] == 1
    assert payload["meta"]["sort"] == {"field": "amount", "direction": "asc"}
    assert len(payload["data"]) == 1
    assert payload["data"][0]["amount"] == 1.234
    assert "sort_value" not in payload["data"][0]


def test_all_forwards_sort_and_disables_limit(capsys):
    assert quotes.main([
        "members", "994612", "--sort", "volume_ratio",
        "--direction", "desc", "--all",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMemberFetcher.calls == [
        ("all", "994612", 100, "volume_ratio", "desc"),
    ]
    assert payload["meta"]["full"] is True
    assert "limit" not in payload["meta"]
    assert payload["data"][0]["volume_ratio"] == 1.234


def test_limit_over_100_uses_bounded_iterator(capsys):
    assert quotes.main([
        "members", "994612", "--sort", "amount", "--limit", "101",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMemberFetcher.calls == [
        ("all", "994612", 100, "amount", "desc"),
    ]
    assert payload["meta"]["full"] is False
    assert payload["meta"]["limit"] == 101
    assert payload["meta"]["count"] == 1


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_limit_must_be_positive(value):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args([
            "members", "994612", "--limit", value,
        ])
    assert exc_info.value.code == 2


def test_limit_and_all_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args([
            "members", "994612", "--limit", "10", "--all",
        ])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("sort_by", ["43", "560", "60", "189", "unknown"])
def test_invalid_sort_is_rejected_by_argparse(sort_by):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args([
            "members", "994612", "--sort", sort_by,
        ])
    assert exc_info.value.code == 2
