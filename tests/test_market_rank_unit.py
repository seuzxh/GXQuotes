#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Action=10006 市场排行单元测试（无网络）。"""

import pytest

from tzt_api import KLineFetcher, MarketRankFetcher, MarketScope
from tzt_api.market_rank import (
    MARKET_RANK_PAGE_MAX,
    MARKET_RANK_PROPS,
    MARKET_RANK_SORT_FIELDS,
    MARKET_SCOPES,
)


@pytest.fixture
def fetcher():
    return MarketRankFetcher()


def _response(*codes):
    count = len(codes)
    raw_by_type = {
        "price": 1_234_000,
        "amount": 1_234_500,
        "volume": 1234,
        "percentage": 1234,
        "ratio": 1234,
    }
    response = {
        "Action": "10006",
        "start": "0",
        "count": str(count),
        "max": "5550",
        "StockCode": list(codes),
        "StockName": [f"股票-{code}" for code in codes],
        "MarketSN": [1, 0, 103][:count],
    }
    for field in MARKET_RANK_SORT_FIELDS.values():
        response[field.raw_key] = [raw_by_type[field.value_type]] * count
    return response


class TestRegistryAndScopes:
    def test_sort_registry_contains_30_verified_fields(self):
        assert len(MARKET_RANK_SORT_FIELDS) == 30
        assert len({field.prop_id for field in MARKET_RANK_SORT_FIELDS.values()}) == 30
        assert MARKET_RANK_SORT_FIELDS["change_pct"].prop_id == 514
        assert MARKET_RANK_SORT_FIELDS["order_ratio"].prop_id == 511
        assert MARKET_RANK_SORT_FIELDS["order_diff"].prop_id == 512
        assert MARKET_RANK_SORT_FIELDS["outside_volume"].prop_id == 22
        assert set(MARKET_RANK_PROPS) == {
            0, 1, 2, *(field.prop_id for field in MARKET_RANK_SORT_FIELDS.values())
        }

    @pytest.mark.parametrize(
        "scope,markettype,routes",
        [
            ("all_a", "JHSASH", (0, 1, 103)),
            ("hs_a", "HSASH", (0, 1)),
            ("sh_a", "SHASH", (1,)),
            ("sz_a", "SZASH", (0,)),
            ("bj_a", "BJASH", (103,)),
            ("main", "HSMAIN", (0, 1)),
            ("gem", "SZGEM", (0,)),
        ],
    )
    def test_scope_registry(self, scope, markettype, routes):
        assert MARKET_SCOPES[scope].markettype == markettype
        assert MARKET_SCOPES[scope].routemarkets == routes

    def test_fetcher_inherits_shared_base(self):
        assert issubclass(MarketRankFetcher, KLineFetcher)


class TestRequestAndParsing:
    def test_default_request_and_full_stable_schema(self, fetcher, monkeypatch):
        captured = {}

        def fake_request(params):
            captured.update(params)
            return _response("600001", "000001", "920001")

        monkeypatch.setattr(fetcher._client, "request", fake_request)
        rows = fetcher.get_market_rank()

        assert captured == {
            "Action": 10006,
            "markettype": "JHSASH",
            "routemarkets": "0,1,103",
            "props": "|".join(str(value) for value in MARKET_RANK_PROPS),
            "sort": 514,
            "direction": 1,
            "start": 0,
            "count": 30,
            "outtype": 1,
        }
        assert len(rows) == 3
        assert set(rows[0]) == {
            "code", "symbol", "name", "market", "market_name",
            *MARKET_RANK_SORT_FIELDS,
        }
        assert rows[0]["symbol"] == "sh600001"
        assert rows[1]["symbol"] == "sz000001"
        assert rows[2]["symbol"] == "bj920001"
        assert rows[0]["price"] == 1.234
        assert rows[0]["amount"] == 123.45
        assert rows[0]["volume"] == 1234.0
        assert rows[0]["change_pct"] == 1.234
        assert rows[0]["volume_ratio"] == 1.234
        assert fetcher.last_rank_meta == {
            "scope": "all_a",
            "scope_label": "京沪深A股",
            "markettype": "JHSASH",
            "routemarkets": [0, 1, 103],
            "start": 0,
            "count": 3,
            "max": 5550,
            "sort": {"field": "change_pct", "direction": "desc"},
        }

    @pytest.mark.parametrize("sort_by,field", MARKET_RANK_SORT_FIELDS.items())
    def test_every_sort_field_maps_to_protocol_id(
        self, fetcher, monkeypatch, sort_by, field,
    ):
        captured = {}

        def fake_request(params):
            captured.update(params)
            return _response("600001")

        monkeypatch.setattr(fetcher._client, "request", fake_request)
        rows = fetcher.get_market_rank(
            "sh-a", start=2, count=1, sort_by=sort_by, direction="asc",
        )

        assert captured["markettype"] == "SHASH"
        assert captured["routemarkets"] == "1"
        assert captured["sort"] == field.prop_id
        assert captured["direction"] == 0
        assert captured["start"] == 2
        assert captured["count"] == 1
        assert field.prop_id in [int(value) for value in captured["props"].split("|")]
        assert sort_by in rows[0]

    def test_custom_scope(self, fetcher, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            fetcher._client,
            "request",
            lambda params: captured.update(params) or _response("123456"),
        )
        custom = MarketScope("custom", "BROKER_X", (8, 9), "券商自定义")

        fetcher.get_market_rank(custom, count=1)

        assert captured["markettype"] == "BROKER_X"
        assert captured["routemarkets"] == "8,9"
        assert fetcher.last_rank_meta["scope"] == "custom"

    def test_missing_and_short_columns_become_none(self, fetcher, monkeypatch):
        response = _response("600001", "000001")
        response.pop("TurnoverRate")
        response["QuoteLast"] = [None]
        response["StockName"] = ["股票一"]
        response["MarketSN"] = [1]
        monkeypatch.setattr(fetcher._client, "request", lambda params: response)

        rows = fetcher.get_market_rank(count=2)

        assert rows[0]["price"] is None
        assert rows[1]["price"] is None
        assert rows[0]["turnover_rate"] is None
        assert rows[1]["turnover_rate"] is None
        assert rows[1]["name"] == ""
        assert rows[1]["market"] is None
        assert rows[1]["symbol"] == "000001"

    def test_invalid_shape_returns_empty_list(self, fetcher, monkeypatch):
        monkeypatch.setattr(fetcher._client, "request", lambda params: {"count": "1"})
        assert fetcher.get_market_rank(count=1) == []

    def test_request_failure_returns_none_and_clears_meta(self, fetcher, monkeypatch):
        fetcher.last_rank_meta = {"old": True}
        monkeypatch.setattr(fetcher._client, "request", lambda params: None)
        assert fetcher.get_market_rank() is None
        assert fetcher.last_rank_meta == {}


class TestValidation:
    @pytest.mark.parametrize("scope", ["unknown", "", 123, None])
    def test_invalid_scope(self, fetcher, scope):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(scope)

    @pytest.mark.parametrize("start", [-1, 1.5, True])
    def test_invalid_start(self, fetcher, start):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(start=start)

    @pytest.mark.parametrize("count", [0, MARKET_RANK_PAGE_MAX + 1, 1.5, True])
    def test_invalid_count(self, fetcher, count):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(count=count)

    @pytest.mark.parametrize("sort_by", ["unknown", 514, None])
    def test_invalid_sort(self, fetcher, sort_by):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(sort_by=sort_by)

    @pytest.mark.parametrize("direction", ["up", 1, None])
    def test_invalid_direction(self, fetcher, direction):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(direction=direction)

    def test_invalid_custom_scope(self, fetcher):
        with pytest.raises(ValueError):
            fetcher.get_market_rank(MarketScope("bad", "", (), "bad"))
