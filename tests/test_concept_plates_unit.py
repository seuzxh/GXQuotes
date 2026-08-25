#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_stock_concept_plates 单元测试：参数构造、关联属性解析、类型标注与过滤。

无需网络与 API，默认运行：
    pytest tests/test_concept_plates_unit.py
"""
import pytest

from tzt_api import ConceptPlateFetcher
from tzt_api.concept_plate import (
    MEMBER_LIST_PROPS,
    MEMBER_SORT_FIELDS,
    PLATE_LIST_PROPS,
    PLATE_SORT_FIELDS,
    PLATE_TYPE_TO_SUBTYPE,
)


@pytest.fixture(scope="module")
def fetcher():
    return ConceptPlateFetcher()


# 实测响应样例（688802 盛美上海，2026-08）
SAMPLE_RESPONSE = {
    "outtype": "1",
    "max": "1",
    "count": "1",
    "props": "900|901|923",
    "CoIndBlkIdx": [{
        "StockCode": ["991334"],
        "MarketSN": [44],
        "StockName": ["半导体类"],
    }],
    "CoBlkIdx": [{
        "StockCode": ["991334", "992023", "994612"],
        "MarketSN": [44, 44, 44],
        "StockName": ["半导体类", "上海", "AI芯片"],
    }],
    "RegionBlkIdx": [{
        "StockCode": ["992023"],
        "MarketSN": [44],
        "StockName": ["上海"],
    }],
}


def _plate_list_response(*codes, maximum=None):
    """Action=10007 列式响应的最小测试样本。"""
    response = {
        "StockCode": list(codes),
        "StockName": [f"板块-{code}" for code in codes],
        "MarketSN": [44] * len(codes),
        "QuoteLast": [1_000_000 + i for i in range(len(codes))],
        "PxChg": [10_000] * len(codes),
        "PxChgPct": [1_000] * len(codes),
    }
    if maximum is not None:
        response["max"] = str(maximum)
    return response


# ============ 0. get_all_plates 类型映射、分页和兼容入口 ============

class TestGetAllPlates:
    def test_sort_registry_matches_scalar_props(self):
        expected_ids = {
            "price": 10,
            "change": 510,
            "change_pct": 514,
            "change_speed_3m_pct": 573,
            "previous_close": 4,
            "previous_change_pct": 575,
            "open": 5,
            "open_change_pct": 574,
            "high": 6,
            "high_change_pct": 576,
            "low": 7,
            "low_change_pct": 577,
            "volume": 12,
            "amount": 13,
            "last_volume": 21,
            "turnover_rate": 551,
            "amplitude": 513,
            "volume_ratio": 521,
            "inside_volume": 23,
            "change_pct_3d": 751,
            "change_pct_5d": 752,
            "change_pct_10d": 753,
            "change_pct_20d": 754,
            "change_pct_60d": 755,
            "change_pct_120d": 756,
            "change_pct_250d": 757,
            "reference_price": 11,
        }
        prop_ids = [field.prop_id for field in PLATE_SORT_FIELDS.values()]
        raw_keys = [field.raw_key for field in PLATE_SORT_FIELDS.values()]

        assert len(PLATE_SORT_FIELDS) == 27
        assert {key: field.prop_id for key, field in PLATE_SORT_FIELDS.items()} == expected_ids
        assert len(prop_ids) == len(set(prop_ids))
        assert len(raw_keys) == len(set(raw_keys))
        assert set(prop_ids) == set(PLATE_LIST_PROPS) - {906}

    def test_plate_list_returns_all_scalar_props_independent_of_sort(
            self, fetcher, monkeypatch):
        raw_by_type = {
            "price": 1_234_000,
            "amount": 1_234_500,
            "volume": 1234,
            "percentage": 1234,
            "ratio": 1234,
        }
        expected_by_type = {
            "price": 1.234,
            "amount": 123.45,
            "volume": 1234.0,
            "percentage": 1.234,
            "ratio": 1.234,
        }

        def fake_request(params):
            response = _plate_list_response("990001", maximum=1)
            for field in PLATE_SORT_FIELDS.values():
                response[field.raw_key] = [raw_by_type[field.value_type]]
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        row = fetcher.get_all_plates(
            sort_by="change_pct_20d",
            limit=1,
        )[0]

        assert set(row) == {"code", "name", "market", *PLATE_SORT_FIELDS}
        for output_name, field in PLATE_SORT_FIELDS.items():
            assert row[output_name] == expected_by_type[field.value_type]
        assert "sort_value" not in row

    def test_all_props_preserve_zero_and_use_none_for_missing_values(
            self, fetcher, monkeypatch):
        def fake_request(params):
            response = _plate_list_response("990001", "990002", maximum=2)
            for field in PLATE_SORT_FIELDS.values():
                response[field.raw_key] = [0, 0]
            response[PLATE_SORT_FIELDS["previous_close"].raw_key] = []
            response[PLATE_SORT_FIELDS["volume_ratio"].raw_key] = [None]
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_all_plates(limit=2)

        assert rows[0]["price"] == 0.0
        assert rows[0]["change_pct"] == 0.0
        assert rows[0]["volume"] == 0.0
        assert rows[0]["previous_close"] is None
        assert rows[1]["previous_close"] is None
        assert rows[0]["volume_ratio"] is None
        assert rows[1]["volume_ratio"] is None

    @pytest.mark.parametrize("plate_type", PLATE_TYPE_TO_SUBTYPE)
    def test_type_maps_to_subtype(self, fetcher, monkeypatch, plate_type):
        captured = {}

        def fake_request(params):
            captured.update(params)
            return _plate_list_response("990001", maximum=1)

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_all_plates(plate_type, limit=1, page_size=50)

        assert len(rows) == 1
        assert captured["Action"] == 10007
        assert captured["market"] == 44
        assert captured["subtype"] == PLATE_TYPE_TO_SUBTYPE[plate_type]
        assert captured["start"] == 0
        assert captured["count"] == 1
        assert captured["sort"] == 514
        assert captured["direction"] == 1

    def test_paginates_until_api_max(self, fetcher, monkeypatch):
        starts = []

        def fake_request(params):
            starts.append(params["start"])
            if params["start"] == 0:
                return _plate_list_response("990001", "990002", maximum=3)
            return _plate_list_response("990003", maximum=3)

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_all_plates("industry", page_size=2)

        assert starts == [0, 2]
        assert [row["code"] for row in rows] == ["990001", "990002", "990003"]
        assert rows[0]["price"] == 1.0
        assert rows[0]["change_pct"] == 1.0

    def test_limit_bounds_request_and_result(self, fetcher, monkeypatch):
        counts = []

        def fake_request(params):
            counts.append(params["count"])
            start = params["start"]
            codes = tuple(f"99{start + i:04d}" for i in range(params["count"]))
            return _plate_list_response(*codes, maximum=100)

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_all_plates("style", limit=3, page_size=2)

        assert counts == [2, 1]
        assert len(rows) == 3

    def test_compatibility_wrapper_delegates(self, fetcher, monkeypatch):
        captured = {}

        def fake_get_all(plate_type, *, limit=None, page_size=100,
                         sort_by="change_pct", direction="desc"):
            captured.update(
                type=plate_type,
                limit=limit,
                page_size=page_size,
                sort_by=sort_by,
                direction=direction,
            )
            return []

        monkeypatch.setattr(fetcher, "get_all_plates", fake_get_all)
        assert fetcher.get_all_concept_plates(
            limit=7,
            page_size=20,
            sort_by="amount",
            direction="asc",
        ) == []
        assert captured == {
            "type": "concept",
            "limit": 7,
            "page_size": 20,
            "sort_by": "amount",
            "direction": "asc",
        }

    @pytest.mark.parametrize("sort_by,field", PLATE_SORT_FIELDS.items())
    def test_sort_field_maps_and_returns_named_value(
            self, fetcher, monkeypatch, sort_by, field):
        raw_by_type = {
            "price": 1_234_000,
            "amount": 1_234_500,
            "volume": 1234,
            "percentage": 1234,
            "ratio": 1234,
        }
        expected_by_type = {
            "price": 1.234,
            "amount": 123.45,
            "volume": 1234.0,
            "percentage": 1.234,
            "ratio": 1.234,
        }
        captured = {}

        def fake_request(params):
            captured.update(params)
            response = _plate_list_response("990001", maximum=1)
            response[field.raw_key] = [raw_by_type[field.value_type]]
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_all_plates(sort_by=sort_by, limit=1)

        assert captured["sort"] == field.prop_id
        assert rows[0][sort_by] == expected_by_type[field.value_type]
        assert set(PLATE_SORT_FIELDS).issubset(rows[0])
        assert "sort_value" not in rows[0]

    @pytest.mark.parametrize("direction,raw", [("asc", 0), ("desc", 1)])
    def test_direction_mapping(self, fetcher, monkeypatch, direction, raw):
        captured = {}

        def fake_request(params):
            captured.update(params)
            return _plate_list_response("990001", maximum=1)

        monkeypatch.setattr(fetcher, "_request", fake_request)
        fetcher.get_all_plates(direction=direction, limit=1)
        assert captured["direction"] == raw

    @pytest.mark.parametrize("sort_by", ["", "906", "lead_stock", "unknown", None, 514])
    def test_invalid_sort_field_raises(self, fetcher, monkeypatch, sort_by):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 sort_by 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_all_plates(sort_by=sort_by)

    @pytest.mark.parametrize("direction", ["", "up", "down", None, 0, 1, True])
    def test_invalid_direction_raises(self, fetcher, monkeypatch, direction):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 direction 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_all_plates(direction=direction)

    @pytest.mark.parametrize("plate_type", ["", "all", "unknown", None, 1])
    def test_invalid_type_raises(self, fetcher, plate_type):
        with pytest.raises(ValueError):
            fetcher.get_all_plates(plate_type)

    @pytest.mark.parametrize("page_size", [0, -1, 101, 1.5, True])
    def test_invalid_page_size_raises(self, fetcher, page_size):
        with pytest.raises(ValueError):
            fetcher.get_all_plates(page_size=page_size)

    @pytest.mark.parametrize("limit", [-1, 0, 1.5, True])
    def test_invalid_limit_raises(self, fetcher, limit):
        with pytest.raises(ValueError):
            fetcher.get_all_plates(limit=limit)


# ============ 1. 10005 成份股排序、方向与分页 ============

class TestGetConceptPlateStocksSort:
    def test_member_sort_registry_matches_numeric_props(self):
        excluded = {43, 560, 60, 61, 62, 189}

        assert len(MEMBER_LIST_PROPS) == 33
        assert len(MEMBER_SORT_FIELDS) == 27
        assert MEMBER_SORT_FIELDS == PLATE_SORT_FIELDS
        assert {field.prop_id for field in MEMBER_SORT_FIELDS.values()} == (
            set(MEMBER_LIST_PROPS) - excluded
        )

    @pytest.mark.parametrize("sort_by,field", MEMBER_SORT_FIELDS.items())
    def test_sort_field_maps_and_returns_named_value(
            self, fetcher, monkeypatch, sort_by, field):
        raw_by_type = {
            "price": 1_234_000,
            "amount": 1_234_500,
            "volume": 1234,
            "percentage": 1234,
            "ratio": 1234,
        }
        expected_by_type = {
            "price": 1.234,
            "amount": 123.45,
            "volume": 1234.0,
            "percentage": 1.234,
            "ratio": 1.234,
        }
        captured = {}

        def fake_request(params):
            captured.update(params)
            response = _plate_list_response("994612", "600001")
            response["MarketSN"] = [44, 1]
            response[field.raw_key] = [0, raw_by_type[field.value_type]]
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        rows = fetcher.get_concept_plate_stocks(
            "994612",
            count=1,
            sort_by=sort_by,
        )

        assert captured["sort"] == field.prop_id
        assert captured["direction"] == 1
        assert captured["props"] == "|".join(map(str, MEMBER_LIST_PROPS))
        assert rows[1][sort_by] == expected_by_type[field.value_type]
        assert "sort_value" not in rows[1]

    @pytest.mark.parametrize("direction,raw", [("asc", 0), ("desc", 1)])
    def test_direction_mapping(self, fetcher, monkeypatch, direction, raw):
        captured = {}

        def fake_request(params):
            captured.update(params)
            response = _plate_list_response("994612", "600001")
            response["MarketSN"] = [44, 1]
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        fetcher.get_concept_plate_stocks(
            "994612",
            count=1,
            direction=direction,
        )
        assert captured["direction"] == raw

    def test_missing_selected_field_is_explicit_none(self, fetcher, monkeypatch):
        response = _plate_list_response("994612", "600001")
        response["MarketSN"] = [44, 1]
        monkeypatch.setattr(fetcher, "_request", lambda params: response)

        rows = fetcher.get_concept_plate_stocks(
            "994612",
            count=1,
            sort_by="amount",
        )

        assert rows[0]["amount"] is None
        assert rows[1]["amount"] is None

    @pytest.mark.parametrize(
        "sort_by",
        ["", "43", "trend", "560", "60", "189", "unknown", None, 514],
    )
    def test_invalid_sort_rejected_before_request(
            self, fetcher, monkeypatch, sort_by):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 sort_by 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_concept_plate_stocks("994612", sort_by=sort_by)

    @pytest.mark.parametrize("direction", ["", "up", "down", None, 0, 1, True])
    def test_invalid_direction_rejected_before_request(
            self, fetcher, monkeypatch, direction):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 direction 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_concept_plate_stocks("994612", direction=direction)

    @pytest.mark.parametrize("start", [-1, 1.5, None, True])
    def test_invalid_start_rejected_before_request(
            self, fetcher, monkeypatch, start):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 start 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_concept_plate_stocks("994612", start=start)

    @pytest.mark.parametrize("count", [0, -1, 101, 1.5, None, True])
    def test_invalid_count_rejected_before_request(
            self, fetcher, monkeypatch, count):
        monkeypatch.setattr(
            fetcher,
            "_request",
            lambda params: pytest.fail("非法 count 不应请求网关"),
        )
        with pytest.raises(ValueError):
            fetcher.get_concept_plate_stocks("994612", count=count)

    @pytest.mark.parametrize("page_size", [0, -1, 101, 1.5, None, True])
    def test_invalid_iterator_page_size(self, fetcher, page_size):
        with pytest.raises(ValueError):
            list(fetcher.iter_concept_plate_stocks(
                "994612",
                page_size=page_size,
            ))

    def test_iterator_forwards_sort_and_advances_by_members(
            self, fetcher, monkeypatch):
        calls = []

        def fake_get(plate_code, start=0, count=10, *,
                     sort_by="change_pct", direction="desc"):
            calls.append((plate_code, start, count, sort_by, direction))
            if start == 0:
                return [
                    {"code": plate_code, "market": 44},
                    {"code": "600001", "market": 1},
                    {"code": "000001", "market": 0},
                ]
            if start == 2:
                return [
                    {"code": plate_code, "market": "44"},
                    {"code": "600002", "market": 1},
                ]
            pytest.fail(f"意外的分页起点: {start}")

        monkeypatch.setattr(fetcher, "get_concept_plate_stocks", fake_get)
        rows = list(fetcher.iter_concept_plate_stocks(
            "994612",
            page_size=2,
            sort_by="amount",
            direction="asc",
        ))

        assert [row["code"] for row in rows] == ["600001", "000001", "600002"]
        assert calls == [
            ("994612", 0, 2, "amount", "asc"),
            ("994612", 2, 2, "amount", "asc"),
        ]

    def test_iterator_stops_when_page_contains_only_plate(
            self, fetcher, monkeypatch):
        monkeypatch.setattr(
            fetcher,
            "get_concept_plate_stocks",
            lambda *args, **kwargs: [{"code": "994612", "market": 44}],
        )
        assert list(fetcher.iter_concept_plate_stocks("994612")) == []


# ============ 2. _parse_plate_group 关联属性解析 ============

class TestParsePlateGroup:
    def test_normal_parse(self, fetcher):
        plates = fetcher._parse_plate_group(SAMPLE_RESPONSE, "CoBlkIdx")
        assert len(plates) == 3
        assert plates[0] == {"code": "991334", "name": "半导体类", "market": 44}
        assert plates[2] == {"code": "994612", "name": "AI芯片", "market": 44}

    def test_missing_key_returns_empty(self, fetcher):
        assert fetcher._parse_plate_group(SAMPLE_RESPONSE, "NotExist") == []

    def test_empty_list_returns_empty(self, fetcher):
        assert fetcher._parse_plate_group({"CoBlkIdx": []}, "CoBlkIdx") == []

    def test_non_dict_inner_returns_empty(self, fetcher):
        assert fetcher._parse_plate_group({"CoBlkIdx": ["xx"]}, "CoBlkIdx") == []

    def test_missing_name_market_tolerated(self, fetcher):
        raw = {"CoBlkIdx": [{"StockCode": ["994612"]}]}
        plates = fetcher._parse_plate_group(raw, "CoBlkIdx")
        assert plates == [{"code": "994612"}]


# ============ 2. get_stock_concept_plates 参数构造与解析 ============

class TestGetStockConceptPlates:
    def _capture(self, fetcher, monkeypatch, response=SAMPLE_RESPONSE):
        captured = {}

        def fake_request(params):
            captured.update(params)
            return response

        monkeypatch.setattr(fetcher, "_request", fake_request)
        return captured

    def test_request_params(self, fetcher, monkeypatch):
        captured = self._capture(fetcher, monkeypatch)
        fetcher.get_stock_concept_plates("688802", 1)
        assert captured["Action"] == 10000
        assert captured["codes"] == "688802|1"
        assert captured["props"] == "900|901|923"
        assert captured["901.props"] == "0|1|2"
        assert captured["900.props"] == "0|1|2"
        assert captured["923.props"] == "0|1|2"
        assert captured["outtype"] == 1

    def test_market_inferred_and_prefix_stripped(self, fetcher, monkeypatch):
        captured = self._capture(fetcher, monkeypatch)
        fetcher.get_stock_concept_plates("sz000001")
        assert captured["codes"] == "000001|0"

    def test_type_annotation(self, fetcher, monkeypatch):
        self._capture(fetcher, monkeypatch)
        plates = fetcher.get_stock_concept_plates("688802", 1)
        by_code = {p["code"]: p["type"] for p in plates}
        assert by_code["991334"] == "industry"
        assert by_code["992023"] == "region"
        assert by_code["994612"] == "concept"

    def test_filter_concept(self, fetcher, monkeypatch):
        self._capture(fetcher, monkeypatch)
        plates = fetcher.get_stock_concept_plates("688802", 1, plate_type="concept")
        assert [p["code"] for p in plates] == ["994612"]

    def test_filter_industry(self, fetcher, monkeypatch):
        self._capture(fetcher, monkeypatch)
        plates = fetcher.get_stock_concept_plates("688802", 1, plate_type="industry")
        assert [p["code"] for p in plates] == ["991334"]

    def test_invalid_plate_type_raises(self, fetcher, monkeypatch):
        self._capture(fetcher, monkeypatch)
        with pytest.raises(ValueError):
            fetcher.get_stock_concept_plates("688802", 1, plate_type="foo")

    def test_request_failure_returns_none(self, fetcher, monkeypatch):
        monkeypatch.setattr(fetcher, "_request", lambda params: None)
        assert fetcher.get_stock_concept_plates("688802", 1) is None

    def test_no_plate_data_returns_empty(self, fetcher, monkeypatch):
        self._capture(fetcher, monkeypatch, response={"props": "900|901|923"})
        assert fetcher.get_stock_concept_plates("688802", 1) == []

    def test_coblkidx_missing_falls_back_to_900_923(self, fetcher, monkeypatch):
        response = {
            "CoIndBlkIdx": SAMPLE_RESPONSE["CoIndBlkIdx"],
            "RegionBlkIdx": SAMPLE_RESPONSE["RegionBlkIdx"],
        }
        self._capture(fetcher, monkeypatch, response=response)
        plates = fetcher.get_stock_concept_plates("688802", 1)
        codes = {p["code"] for p in plates}
        assert codes == {"991334", "992023"}
