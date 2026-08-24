#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityResolver 单元测试：10032 响应解析与路由决策（mock，无网络）。"""
import pytest

from tzt_api import SecurityResolver


def make_resolver(monkeypatch, payload):
    r = SecurityResolver()
    monkeypatch.setattr(r._client, "request", lambda params, **kw: payload)
    return r


MULTI = {  # 实测样例：000001（2026-08-24）
    "ErrorNo": "2", "MaxCount": "2",
    "BinData": "000001|平安银行|000001|上证指数|",
    "StockLabel": "深A|指数|", "MarketNo": "0|1|",
}
UNIQUE_INDEX = {"ErrorNo": "1", "BinData": "000300|沪深300|", "StockLabel": "指数|", "MarketNo": "1|"}


class TestResolve:
    def test_ambiguous_returns_candidates(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("000001")
        assert result["status"] == "ambiguous"
        assert [c["code"] for c in result["candidates"]] == ["000001", "000001"]
        assert [c["is_index"] for c in result["candidates"]] == [False, True]
        assert result["candidates"][1]["market"] == 1

    def test_unique(self, monkeypatch):
        r = make_resolver(monkeypatch, UNIQUE_INDEX)
        result = r.resolve("000300")
        assert result["status"] == "unique"
        assert result["chosen"]["name"] == "沪深300" and result["chosen"]["is_index"]

    def test_prefer_disambiguates(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("000001", prefer="index")
        assert result["status"] == "unique"
        assert result["chosen"]["name"] == "上证指数"

    def test_not_found(self, monkeypatch):
        from tzt_api import TZTAPIError
        r = SecurityResolver()
        def fail(params, **kw):
            r._client.last_error = TZTAPIError("无结果", error_no="-200608")
            return None
        monkeypatch.setattr(r._client, "request", fail)
        assert r.resolve("不存在的标的")["status"] == "not_found"

    def test_name_exact_match_priority(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("平安银行")   # 假设多候选中含名称精确匹配
        assert result["status"] == "unique" and result["chosen"]["name"] == "平安银行"
