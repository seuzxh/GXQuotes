"""Skill ``market-rank`` 子命令单元测试（无网络）。"""

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).parents[1] / "skill" / "scripts" / "quotes.py"
_SPEC = importlib.util.spec_from_file_location("gxquotes_skill_market_rank", _SCRIPT_PATH)
quotes = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(quotes)


class _FakeMarketRankFetcher:
    calls = []

    def __init__(self, strict=False):
        assert strict is True
        self.last_rank_meta = {}

    def get_market_rank(self, scope="all_a", start=0, count=30, *,
                        sort_by="change_pct", direction="desc"):
        self.calls.append((scope, start, count, sort_by, direction))
        self.last_rank_meta = {
            "scope": scope,
            "scope_label": "测试证券池",
            "markettype": "TEST",
            "routemarkets": [0, 1, 103],
            "start": start,
            "count": 1,
            "max": 99,
            "sort": {"field": sort_by, "direction": direction},
        }
        row = {
            "code": "600001",
            "symbol": "sh600001",
            "name": "测试股票",
            "market": 1,
            "market_name": "上证",
        }
        row.update({field: None for field in quotes.MARKET_RANK_SORT_FIELDS})
        row[sort_by] = 1.234
        return [row]


@pytest.fixture(autouse=True)
def fake_fetcher(monkeypatch):
    _FakeMarketRankFetcher.calls = []
    monkeypatch.setattr(quotes, "MarketRankFetcher", _FakeMarketRankFetcher)


def test_default_is_all_a_change_pct_desc_top_30(capsys):
    assert quotes.main(["market-rank"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMarketRankFetcher.calls == [
        ("all_a", 0, 30, "change_pct", "desc"),
    ]
    assert payload["meta"]["count"] == 1
    assert payload["meta"]["max"] == 99
    assert payload["meta"]["scope"] == "all-a"
    assert payload["meta"]["markettype"] == "TEST"
    assert payload["meta"]["routemarkets"] == [0, 1, 103]
    assert payload["meta"]["start"] == 0
    assert payload["meta"]["limit"] == 30
    assert payload["meta"]["sort"] == {
        "field": "change_pct",
        "direction": "desc",
    }
    assert payload["meta"]["retrieved_at"].endswith("Z")
    assert payload["data"][0]["symbol"] == "sh600001"
    assert payload["data"][0]["change_pct"] == 1.234
    assert set(quotes.MARKET_RANK_SORT_FIELDS).issubset(payload["data"][0])


def test_custom_scope_sort_direction_start_and_limit_are_forwarded(capsys):
    assert quotes.main([
        "market-rank", "--scope", "bj-a", "--sort", "order_ratio",
        "--direction", "asc", "--start", "10", "--limit", "5",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert _FakeMarketRankFetcher.calls == [
        ("bj_a", 10, 5, "order_ratio", "asc"),
    ]
    assert payload["meta"]["scope"] == "bj-a"
    assert payload["meta"]["start"] == 10
    assert payload["meta"]["limit"] == 5
    assert payload["meta"]["sort"] == {"field": "order_ratio", "direction": "asc"}
    assert payload["data"][0]["order_ratio"] == 1.234


@pytest.mark.parametrize("value", ["0", "101", "-1", "not-a-number"])
def test_limit_must_be_between_one_and_page_max(value):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["market-rank", "--limit", value])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("value", ["-1", "not-a-number"])
def test_start_must_be_nonnegative(value):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["market-rank", "--start", value])
    assert exc_info.value.code == 2


@pytest.mark.parametrize("sort_by", ["43", "560", "906", "unknown"])
def test_invalid_sort_is_rejected_by_argparse(sort_by):
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["market-rank", "--sort", sort_by])
    assert exc_info.value.code == 2


def test_invalid_scope_is_rejected_by_argparse():
    with pytest.raises(SystemExit) as exc_info:
        quotes.build_parser().parse_args(["market-rank", "--scope", "unknown"])
    assert exc_info.value.code == 2
