#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块集成测试（v1.1.0 重写：pytest 风格，聚焦深度校验与新能力）。

覆盖：板块列表全量分页、快照字段单位换算自洽性、板块K线、成份股（含
板块自身首项行为）、iter_concept_plate_stocks 全量生成器、股票所属板块。

需真实 API（integration marker；跳过条件由 conftest.py 统一处理）：
    pytest tests/test_concept_plates.py -m integration
"""
import pytest

from tzt_api import ConceptPlateFetcher

pytestmark = pytest.mark.integration

TEST_PLATE = "994612"   # AI芯片（成份股总数约 40，见 docs/API/concept_plate_api.md）
TEST_STOCK = "600519"   # 贵州茅台
TEST_MARKET = 1         # 上海


class TestGetAllConceptPlates:
    """全量分页（v1.1.0：此前仅返回前 30 条）。"""

    def test_full_pagination_beyond_single_page(self, plate_fetcher):
        """全量板块数应超过单页上限 100，证明翻页生效（实测总数约 390）。"""
        plates = plate_fetcher.get_all_concept_plates()
        assert plates is not None
        assert len(plates) > 100

    def test_limit_truncates(self, plate_fetcher):
        plates = plate_fetcher.get_all_concept_plates(limit=5)
        assert plates is not None and len(plates) == 5

    def test_fields_complete_and_market_44(self, plate_fetcher):
        plates = plate_fetcher.get_all_concept_plates()
        assert plates
        for plate in plates:
            for field in ("code", "name", "market"):
                assert field in plate and plate[field] is not None
            assert plate["market"] == 44

    def test_snapshot_units_self_consistency(self, plate_fetcher):
        """换算后自洽：change_pct ≈ change / (price - change) × 100（2026-08-24 实测标定）。"""
        plates = plate_fetcher.get_all_concept_plates(limit=10)
        checked = 0
        for p in plates:
            if not all(k in p for k in ("price", "change", "change_pct")):
                continue
            prev = p["price"] - p["change"]
            if prev > 0 and p["change_pct"] != 0:
                implied = p["change"] / prev * 100
                assert abs(implied - p["change_pct"]) < 0.05, (
                    f"{p['code']} change_pct={p['change_pct']} 与 implied={implied:.3f} 不符"
                )
                checked += 1
        assert checked > 0, "样例中无可校验行（快照字段缺失？）"


class TestConceptPlateKline:
    def test_kline_custom_count(self, plate_fetcher):
        data = plate_fetcher.get_concept_plate_kline(TEST_PLATE, count=-10)
        assert data is not None and len(data) > 0
        assert len(data) <= 20  # 请求 10 条，允许小幅冗余

    def test_kline_fields_complete(self, plate_fetcher):
        data = plate_fetcher.get_concept_plate_kline(TEST_PLATE, count=-3)
        required = ["date", "open", "high", "low", "close", "volume", "amount"]
        assert data and all(k in data[-1] for k in required)


class TestConceptPlateStocks:
    def test_single_page_contains_plate_itself_first(self, plate_fetcher):
        """block.include=1：首项为板块自身（market=44），其后为成份股。"""
        stocks = plate_fetcher.get_concept_plate_stocks(TEST_PLATE, start=0, count=5)
        assert stocks is not None and len(stocks) > 0
        assert stocks[0]["market"] == 44
        assert all(s["market"] != 44 for s in stocks[1:])

    def test_snapshot_fields_converted(self, plate_fetcher):
        """v1.1.0 起 price/change/change_pct 已换算（元/点、%），量级合理。"""
        stocks = plate_fetcher.get_concept_plate_stocks(TEST_PLATE, start=0, count=5)
        assert stocks
        for s in stocks:
            if "price" in s:
                assert 0 < s["price"] < 100000
            if "change_pct" in s:
                assert -11 <= s["change_pct"] <= 11

    def test_manual_pagination(self, plate_fetcher):
        page1 = plate_fetcher.get_concept_plate_stocks(TEST_PLATE, start=0, count=5)
        page2 = plate_fetcher.get_concept_plate_stocks(TEST_PLATE, start=5, count=5)
        assert page1 and page2
        codes1 = {s["code"] for s in page1 if s["market"] != 44}
        codes2 = {s["code"] for s in page2}
        assert not (codes1 & codes2), "两页出现重叠"


class TestIterConceptPlateStocks:
    """v1.1.0 新增：自动翻页全量成份股生成器。"""

    def test_full_membership_excludes_plate_itself(self, plate_fetcher):
        stocks = list(plate_fetcher.iter_concept_plate_stocks(TEST_PLATE))
        assert len(stocks) > 10  # 994612 实测约 39 只成份股
        assert all(s["market"] != 44 for s in stocks), "不应包含板块自身（market=44）"
        codes = [s["code"] for s in stocks]
        assert len(codes) == len(set(codes)), "成份股不应重复"

    def test_membership_consistent_with_single_page(self, plate_fetcher):
        """生成器结果与手动首页结果一致（首页剔除板块自身后为前缀）。"""
        full = list(plate_fetcher.iter_concept_plate_stocks(TEST_PLATE, page_size=50))
        page = [s for s in plate_fetcher.get_concept_plate_stocks(TEST_PLATE, start=0, count=50)
                if s["market"] != 44]
        assert [s["code"] for s in full[:len(page)]] == [s["code"] for s in page]


class TestStockConceptPlates:
    def test_fields_and_types(self, plate_fetcher):
        plates = plate_fetcher.get_stock_concept_plates(TEST_STOCK, TEST_MARKET)
        assert plates, "贵州茅台必有所属板块"
        for plate in plates:
            for field in ("code", "name", "market", "type"):
                assert field in plate and plate[field] is not None
            assert plate["type"] in ("industry", "region", "concept")

    def test_filter_concept(self, plate_fetcher):
        concepts = plate_fetcher.get_stock_concept_plates(TEST_STOCK, TEST_MARKET, plate_type="concept")
        assert concepts
        assert all(p["type"] == "concept" for p in concepts)


class TestConceptPlateMinKline:
    """G6：板块分钟行情（2026-08-24 实测网关支持）。"""

    @pytest.mark.parametrize("freq", ["1min", "5min", "15min", "30min", "60min"])
    def test_min_kline_all_freqs(self, plate_fetcher, freq):
        data = plate_fetcher.get_concept_plate_min_kline(TEST_PLATE, freq=freq, count=-3)
        assert data is not None and len(data) > 0
        assert "time" in data[-1] and data[-1]["close"] > 0


class TestConceptPlateTrend:
    """G6：板块分时（2026-08-24 实测网关支持，market=44）。"""

    def test_intraday_trend(self, plate_fetcher):
        """板块分时（当日）：pre_market + trading 两段（2026-08-24 实测 TrendOp 241 点）。"""
        data = plate_fetcher.get_concept_plate_trend(TEST_PLATE)
        assert data is not None
        assert "market_date" in data and "pre_market" in data and "trading" in data

    def test_history_trend(self, plate_fetcher):
        data = plate_fetcher.get_concept_plate_trend(TEST_PLATE, date="20260821")
        assert data is not None and data["trading"]
