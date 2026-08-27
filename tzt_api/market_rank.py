#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Action=10006 市场个股排行封装。"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from tzt_api._base import KLineFetcher
from tzt_api.market import MARKET_CODE_MAP, MARKET_TO_PREFIX
from tzt_api.quote_fields import (
    QUOTE_FIELD_REGISTRY,
    SORT_DIRECTIONS,
    QuoteField,
    convert_quote_value,
)

__all__ = [
    "MARKET_RANK_PAGE_MAX",
    "MARKET_RANK_PROPS",
    "MARKET_RANK_SORT_FIELDS",
    "MARKET_SCOPES",
    "MarketRankFetcher",
    "MarketScope",
]

MARKET_RANK_PAGE_MAX = 100


@dataclass(frozen=True)
class MarketScope:
    """10006 逻辑证券池及其物理市场路由。"""

    key: str
    markettype: str
    routemarkets: Tuple[int, ...]
    label: str


_SZ = MARKET_CODE_MAP["sz"]
_SH = MARKET_CODE_MAP["sh"]
_BJ = MARKET_CODE_MAP["bj"]

MARKET_SCOPES: Dict[str, MarketScope] = {
    "all_a": MarketScope("all_a", "JHSASH", (_SZ, _SH, _BJ), "京沪深A股"),
    "hs_a": MarketScope("hs_a", "HSASH", (_SZ, _SH), "沪深A股"),
    "sh_a": MarketScope("sh_a", "SHASH", (_SH,), "上证A股"),
    "sz_a": MarketScope("sz_a", "SZASH", (_SZ,), "深证A股"),
    "bj_a": MarketScope("bj_a", "BJASH", (_BJ,), "北证A股"),
    "main": MarketScope("main", "HSMAIN", (_SZ, _SH), "沪深主板"),
    "gem": MarketScope("gem", "SZGEM", (_SZ,), "创业板"),
}

# Action 能力必须显式冻结，不能随共享字段注册表未来扩展而未经验证地扩大。
# 下列30项均已于 2026-08-27 对当前网关完成 asc/desc 单页单调性实测。
_MARKET_RANK_SORT_FIELD_NAMES = (
    "price", "change", "change_pct", "change_speed_3m_pct",
    "previous_close", "previous_change_pct", "open", "open_change_pct",
    "high", "high_change_pct", "low", "low_change_pct", "volume",
    "amount", "last_volume", "turnover_rate", "amplitude", "volume_ratio",
    "inside_volume", "change_pct_3d", "change_pct_5d", "change_pct_10d",
    "change_pct_20d", "change_pct_60d", "change_pct_120d",
    "change_pct_250d", "reference_price", "order_ratio", "order_diff",
    "outside_volume",
)
MARKET_RANK_SORT_FIELDS: Dict[str, QuoteField] = {
    name: QUOTE_FIELD_REGISTRY[name] for name in _MARKET_RANK_SORT_FIELD_NAMES
}

# 身份列显式请求，避免依赖券商后台 groups 配置；其余字段固定返回稳定 schema。
MARKET_RANK_PROPS = tuple(dict.fromkeys(
    (0, 1, 2, *(field.prop_id for field in MARKET_RANK_SORT_FIELDS.values()))
))

_MARKET_NAMES = {_SZ: "深证", _SH: "上证", _BJ: "北证"}


class MarketRankFetcher(KLineFetcher):
    """按逻辑市场范围获取服务端排序后的个股行情列表。"""

    def __init__(self, config_path: Optional[str] = None, strict: bool = False):
        super().__init__(config_path=config_path, strict=strict)
        self.last_rank_meta: Dict = {}

    @staticmethod
    def _resolve_scope(scope: Union[str, MarketScope]) -> MarketScope:
        if isinstance(scope, MarketScope):
            if not scope.markettype or not scope.routemarkets:
                raise ValueError("自定义 MarketScope 必须包含 markettype 和 routemarkets")
            return scope
        if not isinstance(scope, str):
            raise ValueError("scope 必须是市场范围名称或 MarketScope")
        key = scope.lower().strip().replace("-", "_")
        if key not in MARKET_SCOPES:
            choices = ", ".join(MARKET_SCOPES)
            raise ValueError(f"无效的 scope: {scope}，可选值: {choices}")
        return MARKET_SCOPES[key]

    @staticmethod
    def _optional_int(value, default=None):
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _field_value(raw: Dict, index: int, field: QuoteField):
        values = raw.get(field.raw_key)
        if not isinstance(values, list) or index >= len(values):
            return None
        try:
            return convert_quote_value(values[index], field)
        except (TypeError, ValueError):
            return None

    def _parse_rows(self, raw: Dict) -> List[Dict]:
        codes = raw.get("StockCode")
        names = raw.get("StockName")
        markets = raw.get("MarketSN")
        if not all(isinstance(values, list) for values in (codes, names, markets)):
            return []

        rows = []
        for index, code in enumerate(codes):
            market = self._optional_int(markets[index]) if index < len(markets) else None
            prefix = MARKET_TO_PREFIX.get(market, "")
            row = {
                "code": str(code),
                "symbol": f"{prefix}{code}" if prefix else str(code),
                "name": names[index] if index < len(names) else "",
                "market": market,
                "market_name": _MARKET_NAMES.get(market),
            }
            for output_name, field in MARKET_RANK_SORT_FIELDS.items():
                row[output_name] = self._field_value(raw, index, field)
            rows.append(row)
        return rows

    def get_market_rank(
        self,
        scope: Union[str, MarketScope] = "all_a",
        start: int = 0,
        count: int = 30,
        *,
        sort_by: str = "change_pct",
        direction: str = "desc",
    ) -> Optional[List[Dict]]:
        """获取市场个股排行（单页，最多100条）。

        ``scope`` 可使用内置范围名称或自定义 ``MarketScope``；普通调用方应优先
        使用内置范围，避免 markettype 与 routemarkets 错配。实时排行跨页不是
        强一致快照，因此本方法只提供显式单页窗口。
        """

        resolved_scope = self._resolve_scope(scope)
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise ValueError("start 必须是非负整数")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MARKET_RANK_PAGE_MAX:
            raise ValueError(f"count 必须是 1 到 {MARKET_RANK_PAGE_MAX} 之间的整数")
        if not isinstance(sort_by, str):
            raise ValueError("sort_by 必须是排序字段的英文键")
        sort_by = sort_by.lower().strip()
        if sort_by not in MARKET_RANK_SORT_FIELDS:
            choices = ", ".join(MARKET_RANK_SORT_FIELDS)
            raise ValueError(f"无效的 sort_by: {sort_by}，可选值: {choices}")
        if not isinstance(direction, str):
            raise ValueError("direction 必须是 asc 或 desc")
        direction = direction.lower().strip()
        if direction not in SORT_DIRECTIONS:
            raise ValueError("无效的 direction，可选值: asc, desc")

        sort_field = MARKET_RANK_SORT_FIELDS[sort_by]
        props = list(MARKET_RANK_PROPS)
        if sort_field.prop_id not in props:
            props.append(sort_field.prop_id)

        params = {
            "Action": 10006,
            "markettype": resolved_scope.markettype,
            "routemarkets": ",".join(str(value) for value in resolved_scope.routemarkets),
            "props": "|".join(str(prop_id) for prop_id in props),
            "sort": sort_field.prop_id,
            "direction": SORT_DIRECTIONS[direction],
            "start": start,
            "count": count,
            "outtype": 1,
        }
        raw = self._client.request(params)
        if raw is None:
            self.last_rank_meta = {}
            return None

        rows = self._parse_rows(raw)
        self.last_rank_meta = {
            "scope": resolved_scope.key,
            "scope_label": resolved_scope.label,
            "markettype": resolved_scope.markettype,
            "routemarkets": list(resolved_scope.routemarkets),
            "start": self._optional_int(raw.get("start"), start),
            "count": len(rows),
            "max": self._optional_int(raw.get("max")),
            "sort": {"field": sort_by, "direction": direction},
        }
        return rows
