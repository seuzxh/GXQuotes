#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指数行情集成测试（v2：显式前缀形式，原白名单参数化已随 INDEX_CODE_MAP 删除）。"""
import pytest

pytestmark = pytest.mark.integration

from tzt_api import KLineFetcher, MinKLineFetcher, TrendFetcher, AmbiguousCodeError

# 显式前缀 × 市场 × 名称（v2 契约：指数一律显式前缀，与 qlib SH000300 同构）
EXPLICIT_INDICES = [
    ("sh000001", 1, "上证指数"), ("sh000010", 1, "上证180"), ("sh000016", 1, "上证50"),
    ("sh000300", 1, "沪深300"), ("sh000688", 1, "科创50"), ("sh000852", 1, "中证1000"),
    ("sh000903", 1, "中证100"), ("sh000905", 1, "中证500"), ("sh000906", 1, "中证800"),
    ("sh000922", 1, "中证红利"), ("sh932000", 1, "中证2000"),
    ("sz399001", 0, "深证成指"), ("sz399004", 0, "深证100"), ("sz399006", 0, "创业板指"),
    ("sz399102", 0, "创业板综"), ("sz399295", 0, "创业板50"), ("sz399303", 0, "国证2000"),
    ("sz399971", 0, "中证传媒"), ("sz399997", 0, "中证白酒"),
    ("bj899050", 103, "北证50"),
]


class TestExplicitIndexKline:
    @pytest.mark.parametrize("code,market,name", EXPLICIT_INDICES,
                             ids=[c[2] for c in EXPLICIT_INDICES])
    def test_day_kline(self, day_fetcher, code, market, name):
        data = day_fetcher.fetch_day_kline(code, count=-1, adjust="none")
        assert data is not None and len(data) > 0, f"{code} {name} 日K无数据"


class TestV2BareIndexCodes:
    def test_bare_000_raises_before_request(self, day_fetcher):
        """裸 000xxx 在参数构造期抛异常——不发请求即失败。"""
        with pytest.raises(AmbiguousCodeError):
            day_fetcher.fetch_day_kline("000300", count=-1)

    def test_bare_399_now_unknown(self, day_fetcher):
        """v2 破坏性示例：裸 399001 不再按深市指数推断。"""
        from tzt_api import UnknownCodeError
        with pytest.raises(UnknownCodeError):
            day_fetcher.fetch_day_kline("399001", count=-1)
