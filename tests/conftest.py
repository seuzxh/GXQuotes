#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试共享基础设施（v1.1.0 收敛）。

- 集成测试跳过条件单点定义：未设置 KLINE_API_BASE_URL 时自动跳过
  integration 标记的用例（此前 4 个文件逐字重复 pytestmark 块）
- session 级共享 Fetcher fixtures：集成测试文件统一从这里取用
  （单测文件因需 monkeypatch 实例，保留各自的局部 fixture）
"""
import os

import pytest

from tzt_api import KLineFetcher, MinKLineFetcher, ConceptPlateFetcher, TrendFetcher


def pytest_collection_modifyitems(config, items):
    if os.environ.get("KLINE_API_BASE_URL"):
        return
    skip = pytest.mark.skip(reason="需要设置 KLINE_API_BASE_URL 环境变量才能运行集成测试")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def day_fetcher():
    return KLineFetcher()


@pytest.fixture(scope="session")
def min_fetcher():
    return MinKLineFetcher()


@pytest.fixture(scope="session")
def plate_fetcher():
    return ConceptPlateFetcher()


@pytest.fixture(scope="session")
def trend_fetcher():
    return TrendFetcher()
