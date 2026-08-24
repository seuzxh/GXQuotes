"""tzt-api：中焯行情 3.0 API 客户端（A股日K/分钟K/概念板块/分时）。

公开 API：
    KLineFetcher           — 基类（日K线 + 共享底座）
    MinKLineFetcher        — 分钟K线（继承 KLineFetcher）
    ConceptPlateFetcher    — 概念板块（继承 KLineFetcher）
    TrendFetcher           — 分时数据（继承 KLineFetcher）
    AdjustType             — 复权方式枚举
    TZTClient              — 共享传输层（会话/进程级限流/重试，v1.1.0）
    TZTError / TZTConnectionError / TZTAPIError — 类型化异常（v1.1.0，strict 模式）
    MarketResolutionError / AmbiguousCodeError / UnknownCodeError
                           — v2 市场解析异常（market.py v2 契约，随 v2.0.0 发版）

市场规则（与 kline-qlib 共享的单一事实源）见 tzt_api.market。
qlib 数据转换/下载见 kline-qlib 包。

⚠️ v2.0.0 待发版：market.py 已切换 v2 显式契约（零指数知识段位规则 +
Ambiguous/Unknown 异常，破坏性变更），版本号将于 v2.0.0 发版时同步提升。
"""
from tzt_api._base import KLineFetcher, AdjustType
from tzt_api._transport import TZTClient, TZTError, TZTConnectionError, TZTAPIError
from tzt_api.min_kline import MinKLineFetcher
from tzt_api.concept_plate import ConceptPlateFetcher
from tzt_api.trend import TrendFetcher
from tzt_api.market import (
    MarketResolutionError,
    AmbiguousCodeError,
    UnknownCodeError,
)

__all__ = [
    "KLineFetcher",
    "MinKLineFetcher",
    "ConceptPlateFetcher",
    "TrendFetcher",
    "AdjustType",
    "TZTClient",
    "TZTError",
    "TZTConnectionError",
    "TZTAPIError",
    "MarketResolutionError",
    "AmbiguousCodeError",
    "UnknownCodeError",
]
__version__ = "1.1.0"
