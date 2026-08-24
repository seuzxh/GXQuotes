#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityResolver 集成测试（真实网关，2026-08-24 实测样例固化）。"""
import pytest

pytestmark = pytest.mark.integration

from tzt_api import SecurityResolver


@pytest.fixture(scope="module")
def resolver():
    return SecurityResolver()


class TestResolveIntegration:
    def test_unique_index_bare_code(self, resolver):
        r = resolver.resolve("000300")
        assert r["status"] == "unique" and r["chosen"]["is_index"] and r["chosen"]["market"] == 1

    def test_ambiguous_000001(self, resolver):
        r = resolver.resolve("000001")
        assert r["status"] == "ambiguous" and len(r["candidates"]) == 2

    def test_prefer_index(self, resolver):
        r = resolver.resolve("000001", prefer="index")
        assert r["status"] == "unique" and r["chosen"]["name"] == "上证指数"

    def test_chinese_name(self, resolver):
        r = resolver.resolve("贵州茅台")
        assert r["status"] == "unique" and r["chosen"]["code"] == "600519"

    def test_pinyin_fuzzy_multi(self, resolver):
        r = resolver.resolve("zs")
        assert r["status"] == "ambiguous" and len(r["candidates"]) > 1

    def test_not_found(self, resolver):
        r = resolver.resolve("zzzzzz9999")
        assert r["status"] == "not_found"
