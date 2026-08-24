#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""market.py v2 契约测试：段位规则（10032 实测标定）+ 解析异常。"""
import pytest

from tzt_api import AmbiguousCodeError, UnknownCodeError
from tzt_api.market import MARKET_CODE_MAP, MARKET_TO_PREFIX, numeric_code, infer_market


class TestNumericCode:
    def test_strips_prefixes(self):
        assert numeric_code("sh600519") == "600519"
        assert numeric_code("SZ000001") == "000001"
        assert numeric_code("bj830799") == "830799"

    def test_bare_passthrough(self):
        assert numeric_code("600519") == "600519"


class TestInferMarketExplicitPrefix:
    """显式前缀 > 一切（个股/指数通用，共用命名空间）。"""

    def test_prefixes(self):
        assert infer_market("sh600519") == 1
        assert infer_market("SH000300") == 1      # 指数走同一前缀命名空间
        assert infer_market("sz000001") == 0      # 平安银行
        assert infer_market("SZ399001") == 0      # 深证成指
        assert infer_market("bj899050") == 103    # 北证50
        assert infer_market("Bj830799") == 103


class TestInferMarketSegments:
    """裸码个股段位直判（2026-08-24/25 10032 实测标定）。"""

    @pytest.mark.parametrize("code", ["600000", "601318", "603259", "605499",
                                      "688981", "689009", "900948"])
    def test_sh_segments(self, code):
        assert infer_market(code) == 1            # 900=沪B（实测补入）

    @pytest.mark.parametrize("code", ["001979", "002594", "003816", "300750", "301269"])
    def test_sz_segments(self, code):
        assert infer_market(code) == 0

    @pytest.mark.parametrize("code", ["920001", "920002", "920100"])
    def test_bj_segments(self, code):
        assert infer_market(code) == 103          # 920=北交所现行码段（2026 切换后）


class TestAmbiguous:
    @pytest.mark.parametrize("code", ["000001", "000002", "000016", "000300", "000688",
                                      "000905", "000852", "000858", "000333", "000651"])
    def test_000_segment_raises(self, code):
        """000xxx 整段抛异常——实测 7/11 双候选，静态不可分。"""
        with pytest.raises(AmbiguousCodeError) as ei:
            infer_market(code)
        assert "sz" in str(ei.value) and "sh" in str(ei.value)  # 消息含行动指引


class TestUnknown:
    @pytest.mark.parametrize("code", ["200002", "932000", "930050", "921000",
                                      "830799", "870357", "430047", "899050",
                                      "123456", "5"])
    def test_unknown_raises(self, code):
        """未知段位 fail-fast（200 深B 网关无数据；93x 中证需显式前缀；
        83/43/87 北交所旧码已切换 920 段；899 北证指数需 bj 前缀；921-929 未分配）。"""
        with pytest.raises(UnknownCodeError):
            infer_market(code)

    def test_legacy_bse_hint(self):
        """北交所旧码的错误消息含 920 切换指引（2026-08-25 实测标签「已切换」）。"""
        with pytest.raises(UnknownCodeError) as ei:
            infer_market("830799")
        assert "920" in str(ei.value)


class TestV2Removals:
    def test_whitelist_removed(self):
        """v2.0.0：指数白名单与指数优先判定全部删除。"""
        import tzt_api.market as m
        assert not hasattr(m, "INDEX_CODE_MAP")
        assert not hasattr(m, "INDEX_CODE_PREFIXES")
        assert not hasattr(m, "is_index")
        assert not hasattr(m, "get_index_info")


class TestTables:
    def test_maps_kept(self):
        assert MARKET_CODE_MAP == {"sh": 1, "sz": 0, "bj": 103}
        assert MARKET_TO_PREFIX == {1: "sh", 0: "sz", 103: "bj"}
