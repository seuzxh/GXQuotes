#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市场规则单一事实源（v2 显式契约）：段位规则纯函数 + 解析异常。

v2.0.0 契约（设计存档 2026-08-24-market-v2-and-routing-design.md）：
  - 前缀 = 市场声明，个股与指数共用 sh/sz/bj 命名空间（对齐 qlib SH000300）
  - 零指数知识：仅个股段位规则（2026-08-24 经 10032 全段实测标定）
  - 000xxx 裸码歧义（深市个股/沪市指数实测共存）→ AmbiguousCodeError
  - 未知段位 → UnknownCodeError（fail-fast，替换 v1 "默认深"）
v1 的指数白名单与指数优先判定（含指数查询辅助函数）已删除（破坏性变更，
删除符号清单见 CHANGELOG 2.0.0 节与设计存档）。
被 tzt-api 与 kline-qlib 共享。零第三方依赖。
"""

__all__ = [
    "MarketResolutionError",
    "AmbiguousCodeError",
    "UnknownCodeError",
    "MARKET_CODE_MAP",
    "MARKET_TO_PREFIX",
    "numeric_code",
    "infer_market",
]

# 市场 → 中焯市场代码（sh=沪 1, sz=深 0, bj=北 103）
MARKET_CODE_MAP = {"sh": 1, "sz": 0, "bj": 103}

# 反查表：市场代码 → qlib 目录前缀（下游 converter 的 code_to_qlib_dir 使用）
MARKET_TO_PREFIX = {1: "sh", 0: "sz", 103: "bj"}

# 个股段位规则（前缀匹配，全部 10032 实测标定，见设计存档 §1.4）
SH_SEGMENTS = ("600", "601", "603", "605", "688", "689", "900")  # 900=沪B
SZ_SEGMENTS = ("001", "002", "003", "300", "301")
BJ_SEGMENTS = ("920",)  # 北交所现行码段（2026 由 83/43/87 切换而来；921-929 未分配）
LEGACY_BSE_PREFIXES = ("8", "4")  # 旧北交所码（网关标签「已切换」，别名仍可取数）

# 歧义段：深市个股与沪市指数真实共存（实测 11 样本 7 双候选），静态不可分
AMBIGUOUS_SEGMENTS = ("000",)


class MarketResolutionError(ValueError):
    """标的代码无法解析为市场（v2 解析异常基类）。"""


class AmbiguousCodeError(MarketResolutionError):
    """歧义代码：000xxx 裸码在深市个股与沪市指数两个市场同时存在真实证券。"""


class UnknownCodeError(MarketResolutionError):
    """未知段位代码：v2 起 fail-fast，不再默认深市。"""


def numeric_code(code: str) -> str:
    """剥离 sh/sz/bj 显式前缀，返回纯数字代码。无前缀则原样返回。"""
    upper = code.upper()
    if upper[:2] in ("SH", "SZ", "BJ"):
        return code[2:]
    return code


def infer_market(code: str) -> int:
    """推断市场代码（v2 契约：显式前缀 > 个股段位 > 异常）。

    判断顺序：
      1. 显式前缀 sh/sz/bj → 对应市场（个股/指数通用）
      2. 个股段位：600/601/603/605/688/689/900→沪；001/002/003/300/301→深；
         920→北（北交所现行码段，2026 由 83/43/87 切换而来）
      3. 000xxx → AmbiguousCodeError（消息含 sz/sh 行动指引）
      4. 其余 → UnknownCodeError（8/4 开头的北交所旧码给 920 切换指引）

    ⚠️ v2 破坏性变更：指数裸码（含 399xxx/93xxxx/000xxx）与北交所旧码
    （83/43/87，已切换至 920 段）不再推断——请用显式前缀
    （sz399001 / sh932000 / sh000300）、920 新码，或显式传 market。
    """
    upper = code.upper()
    if upper.startswith("SH"):
        return MARKET_CODE_MAP["sh"]
    if upper.startswith("SZ"):
        return MARKET_CODE_MAP["sz"]
    if upper.startswith("BJ"):
        return MARKET_CODE_MAP["bj"]

    numeric = numeric_code(code)
    if numeric.startswith(AMBIGUOUS_SEGMENTS):
        raise AmbiguousCodeError(
            f"{code} 为歧义代码（深市个股/沪市指数共存）："
            f"个股请用 sz{numeric}，指数请用 sh{numeric}，或显式传 market"
        )
    if numeric.startswith(SH_SEGMENTS):
        return MARKET_CODE_MAP["sh"]
    if numeric.startswith(SZ_SEGMENTS):
        return MARKET_CODE_MAP["sz"]
    if numeric.startswith(BJ_SEGMENTS):
        return MARKET_CODE_MAP["bj"]
    if numeric.startswith(LEGACY_BSE_PREFIXES):
        raise UnknownCodeError(
            f"{code} 为北交所旧码（已切换至 920 段）或新三板代码："
            f"请改用 920 新码（可用 SecurityResolver 查询），"
            f"或显式传 market=103 使用旧码别名"
        )
    raise UnknownCodeError(
        f"{code} 属未知段位，无法推断市场；请使用 sh/sz/bj 前缀或显式传 market"
    )
