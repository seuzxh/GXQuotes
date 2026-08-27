#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Action=10006 市场排行真实接口测试。"""

import pytest

from tzt_api import MarketRankFetcher
from tzt_api.market_rank import MARKET_RANK_SORT_FIELDS, MARKET_SCOPES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fetcher():
    return MarketRankFetcher(strict=True)


@pytest.mark.parametrize("scope", MARKET_SCOPES)
def test_scope_returns_only_configured_markets(fetcher, scope):
    rows = fetcher.get_market_rank(scope, count=5)
    assert rows
    allowed = set(MARKET_SCOPES[scope].routemarkets)
    assert {row["market"] for row in rows}.issubset(allowed)
    assert fetcher.last_rank_meta["markettype"] == MARKET_SCOPES[scope].markettype


@pytest.mark.parametrize("direction,reverse", [("asc", False), ("desc", True)])
@pytest.mark.parametrize("sort_by,field", MARKET_RANK_SORT_FIELDS.items())
def test_every_public_sort_field_is_server_sorted(
    fetcher, sort_by, field, direction, reverse,
):
    rows = fetcher.get_market_rank(
        "all_a", count=5, sort_by=sort_by, direction=direction,
    )
    values = [row[sort_by] for row in rows if row[sort_by] is not None]
    assert values
    assert values == sorted(values, reverse=reverse)
    assert field.raw_key


def test_ascending_and_page_metadata(fetcher):
    rows = fetcher.get_market_rank(
        "all_a", start=0, count=10, sort_by="change_pct", direction="asc",
    )
    values = [row["change_pct"] for row in rows if row["change_pct"] is not None]
    assert values == sorted(values)
    assert fetcher.last_rank_meta["start"] == 0
    assert fetcher.last_rank_meta["count"] == len(rows)
    assert fetcher.last_rank_meta["max"] >= len(rows)


def test_price_change_percentage_units_are_self_consistent(fetcher):
    rows = fetcher.get_market_rank("all_a", count=20)
    checked = 0
    for row in rows:
        if None in (row["price"], row["change"], row["reference_price"]):
            continue
        assert row["price"] == pytest.approx(
            row["reference_price"] + row["change"], abs=0.02,
        )
        checked += 1
    assert checked > 0
