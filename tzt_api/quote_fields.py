#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""普通行情字段元数据与统一单位换算。

字段 ID、网关响应键和值类型来自中焯官方属性表，并经 10005/10006/10007
真实请求校验。各 Action 是否支持某字段排序由各自模块维护能力集合；本模块只
提供跨接口共享的字段事实，避免在板块排行、板块成份股和市场排行中重复定义。
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

__all__ = [
    "QuoteField",
    "QUOTE_FIELD_REGISTRY",
    "SORT_DIRECTIONS",
    "convert_quote_value",
]


@dataclass(frozen=True)
class QuoteField:
    """一个可请求的普通标量行情字段。"""

    prop_id: int
    raw_key: str
    label: str
    value_type: str
    stock_unit: str
    plate_label: Optional[str] = None
    plate_unit: Optional[str] = None


# 顺序即对外稳定字段顺序。前 27 项与既有 10005/10007 排序契约一致；
# 511/512/22 为 10006 真实请求字段，并于 2026-08-27 完成双方向排序实测。
QUOTE_FIELD_REGISTRY: Dict[str, QuoteField] = {
    "price": QuoteField(10, "QuoteLast", "最新价", "price", "元", "最新点位", "点"),
    "change": QuoteField(510, "PxChg", "涨跌额", "price", "元", "涨跌", "点"),
    "change_pct": QuoteField(514, "PxChgPct", "涨跌幅", "percentage", "%"),
    "change_speed_3m_pct": QuoteField(573, "3MinPxChg", "3分钟涨速", "percentage", "%"),
    "previous_close": QuoteField(4, "PreClose", "昨收", "price", "元", plate_unit="点"),
    "previous_change_pct": QuoteField(575, "PrePxChgPct", "昨日涨跌幅", "percentage", "%"),
    "open": QuoteField(5, "Open", "今开", "price", "元", plate_unit="点"),
    "open_change_pct": QuoteField(574, "OpenPxChgPct", "开盘涨跌幅", "percentage", "%"),
    "high": QuoteField(6, "High", "最高", "price", "元", plate_unit="点"),
    "high_change_pct": QuoteField(576, "HighPxChgPct", "最高涨跌幅", "percentage", "%"),
    "low": QuoteField(7, "Low", "最低", "price", "元", plate_unit="点"),
    "low_change_pct": QuoteField(577, "LowPxChgPct", "最低涨跌幅", "percentage", "%"),
    "volume": QuoteField(12, "Volume", "总成交量", "volume", "股"),
    "amount": QuoteField(13, "Turnover", "总成交额", "amount", "元"),
    "last_volume": QuoteField(21, "NewVol", "现手", "volume", "股"),
    "turnover_rate": QuoteField(551, "TurnoverRate", "换手率", "percentage", "%"),
    "amplitude": QuoteField(513, "Amplitude", "振幅", "percentage", "%"),
    "volume_ratio": QuoteField(521, "VolRelRatio", "量比", "ratio", "倍"),
    "inside_volume": QuoteField(23, "Inside", "内盘", "volume", "股"),
    "change_pct_3d": QuoteField(751, "PxChgPct3TD", "3日涨幅", "percentage", "%"),
    "change_pct_5d": QuoteField(752, "PxChgPct5TD", "5日涨幅", "percentage", "%"),
    "change_pct_10d": QuoteField(753, "PxChgPct10TD", "10日涨幅", "percentage", "%"),
    "change_pct_20d": QuoteField(754, "PxChgPct20TD", "20日涨幅", "percentage", "%"),
    "change_pct_60d": QuoteField(755, "PxChgPct60TD", "60日涨幅", "percentage", "%"),
    "change_pct_120d": QuoteField(756, "PxChgPct120TD", "120日涨幅", "percentage", "%"),
    "change_pct_250d": QuoteField(757, "PxChgPct250TD", "250日涨幅", "percentage", "%"),
    "reference_price": QuoteField(11, "QuotePreClose", "报价基准价", "price", "元", plate_unit="点"),
    "order_ratio": QuoteField(511, "OrderRatio", "委比", "percentage", "%"),
    "order_diff": QuoteField(512, "OrderDiff", "委差", "volume", "股"),
    "outside_volume": QuoteField(22, "Outside", "外盘", "volume", "股"),
}

SORT_DIRECTIONS = {"asc": 0, "desc": 1}


def convert_quote_value(raw: Any, field: QuoteField):
    """把网关原始值换算为项目统一单位；空值原样返回。"""

    if raw is None:
        return None
    if field.value_type == "price":
        return round(raw / 1_000_000, 4)
    if field.value_type == "amount":
        return round(raw / 10_000, 2)
    if field.value_type == "volume":
        return float(raw)
    if field.value_type in ("percentage", "ratio"):
        return round(raw / 1_000, 3)
    raise ValueError(f"未知行情字段值类型: {field.value_type}")
