#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tzt-api 包结构静态测试。"""


class TestTztApiStructure:
    def test_exports(self):
        import tzt_api
        assert set(tzt_api.__all__) == {
            "KLineFetcher", "MinKLineFetcher", "ConceptPlateFetcher",
            "TrendFetcher", "AdjustType",
            "TZTClient", "TZTError", "TZTConnectionError", "TZTAPIError",
            "MarketResolutionError", "AmbiguousCodeError", "UnknownCodeError",
            "SecurityResolver",
        }
        assert tzt_api.__version__ == "1.1.0"  # v2.0.0 待发版（M2 Task 8 提升）

    def test_module_location(self):
        from tzt_api import KLineFetcher
        assert KLineFetcher.__module__ == "tzt_api._base"

    def test_inheritance_chain(self):
        from tzt_api import KLineFetcher, MinKLineFetcher, ConceptPlateFetcher, TrendFetcher
        for cls in (MinKLineFetcher, ConceptPlateFetcher, TrendFetcher):
            assert issubclass(cls, KLineFetcher)

    def test_transport_composition(self):
        """v1.1.0：传输层组合——Fetcher 持有 TZTClient，_request 为薄委托。"""
        from tzt_api import KLineFetcher, TZTClient
        from tzt_api._transport import TZTError, TZTConnectionError, TZTAPIError
        assert TZTClient.__module__ == "tzt_api._transport"
        assert issubclass(TZTConnectionError, TZTError)
        assert issubclass(TZTAPIError, TZTError)
        assert hasattr(KLineFetcher, "_request")
        assert hasattr(KLineFetcher, "_throttle")

    def test_method_attribution(self):
        from tzt_api import KLineFetcher, MinKLineFetcher, ConceptPlateFetcher
        for m in ["fetch_day_kline", "fetch_day_kline_with_factor",
                  "fetch_trade_calendar", "get_stock_info", "infer_market"]:
            assert hasattr(KLineFetcher, m), f"KLineFetcher 缺 {m}"
        for m in ["fetch_min_kline", "get_all_concept_plates", "get_concept_plate_kline"]:
            assert not hasattr(KLineFetcher, m), f"KLineFetcher 不应有 {m}"
        for m in ["is_index", "get_index_info"]:
            assert not hasattr(KLineFetcher, m), f"v2 已删除 {m}"
        assert hasattr(MinKLineFetcher, "fetch_min_kline")
        assert not hasattr(KLineFetcher, "get_concept_plate_min_kline")
        assert hasattr(ConceptPlateFetcher, "get_concept_plate_min_kline")
        assert hasattr(KLineFetcher, "_fetch_kline_series")   # 私有共享实现上移基类
        assert hasattr(ConceptPlateFetcher, "get_all_concept_plates")
        assert hasattr(ConceptPlateFetcher, "iter_concept_plate_stocks"), \
            "ConceptPlateFetcher 缺 v1.1.0 新增的 iter_concept_plate_stocks"

    def test_v2_market_exports(self):
        from tzt_api import MarketResolutionError, AmbiguousCodeError, UnknownCodeError
        from tzt_api.market import SH_SEGMENTS, SZ_SEGMENTS, BJ_SEGMENTS, AMBIGUOUS_SEGMENTS
        assert issubclass(AmbiguousCodeError, MarketResolutionError)
        assert issubclass(UnknownCodeError, MarketResolutionError)
        assert issubclass(MarketResolutionError, ValueError)

    def test_module_all_declarations(self):
        from tzt_api import _base, min_kline, concept_plate, trend, market, _transport
        for mod in (_base, min_kline, concept_plate, trend, market, _transport):
            assert hasattr(mod, "__all__")
