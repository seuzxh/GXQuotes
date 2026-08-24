#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分钟K线获取：1min / 5min / 15min / 30min / 60min。

继承 KLineFetcher 获得 _request / _build_params / _parse_kline_items 等底座。
v2.0.0 起 freq→klinetype 映射、locator 翻页、去重排序的实现体上移为基类
KLineFetcher._fetch_kline_series（供板块分钟K复用），本类的 fetch_min_kline
为保留公开签名的薄委托。
"""

from typing import Dict, List, Optional

from tzt_api._base import KLineFetcher

__all__ = ["MinKLineFetcher"]


class MinKLineFetcher(KLineFetcher):
    """分钟K线获取客户端。

    相较基类 KLineFetcher（日K），本类提供分钟频率特有的能力：
      - fetch_min_kline：按 freq 获取分钟K线，支持 locator 自动翻页、去重排序
        （实现体为基类 KLineFetcher._fetch_kline_series 的薄委托，v2.0.0）

    返回数据自带 date/time 字段，客户端可自行按时间切片，无需专门的时间定位方法。

    使用示例:
        >>> fetcher = MinKLineFetcher()
        >>> data = fetcher.fetch_min_kline("600519", freq="5min", count=-500)
    """

    def fetch_min_kline(self, code: str, freq: str = "1min", count: Optional[int] = None, market: Optional[int] = None, pages: int = 1, adjust: Optional[str] = None) -> Optional[List[Dict]]:
        return self._fetch_kline_series(code, freq=freq, count=count, market=market,
                                        pages=pages, adjust=adjust)

