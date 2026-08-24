#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分时数据获取：当日分时、历史分时。

继承 KLineFetcher 获得 _request / infer_market 等底座，
本类专注分时数据的公开入口：fetch_intraday_trend / fetch_history_trend / fetch_trend。
v2.0.0 起 Action=10001 参数构造（_build_trend_params）、CallTrend/TrendOp 解析
（_parse_call_trend / _parse_trend_op / _convert_trend_time）与统一请求实现
（_fetch_trend_raw）上移为 KLineFetcher 基类方法（供板块分时复用），
本类经继承使用，公开签名与返回结构不变。
"""

from typing import Dict, List, Optional

from tzt_api._base import KLineFetcher

__all__ = ["TrendFetcher"]


class TrendFetcher(KLineFetcher):
    """分时数据获取客户端。

    提供分时数据获取能力：
      - fetch_intraday_trend：获取当日分时数据
      - fetch_history_trend：获取历史分时数据

    使用示例:
        >>> fetcher = TrendFetcher()
        >>> # 当日分时
        >>> data = fetcher.fetch_intraday_trend("600519")
        >>> # 历史分时
        >>> data = fetcher.fetch_history_trend("600519", "20260611")
    """

    def fetch_intraday_trend(self, code: str, market: Optional[int] = None) -> Optional[Dict[str, List[Dict]]]:
        """获取当日分时数据（date=0, daycount=0）

        Args:
            code: 股票代码，支持 "600519", "SH600519" 等格式
            market: 市场代码，可选，自动推断

        Returns:
            Dict 包含:
                - pre_market: 盘前数据列表
                - trading: 盘中数据列表
                - market_date: 市场日期
        """
        return self._fetch_trend_raw(code, date=0, daycount=0, market=market, label="intraday")

    def fetch_history_trend(self, code: str, date: str, market: Optional[int] = None) -> Optional[Dict[str, List[Dict]]]:
        """获取历史分时数据（date指定日期, daycount=1）

        Args:
            code: 股票代码，支持 "600519", "SH600519" 等格式
            date: 历史日期，格式 "YYYYMMDD"
            market: 市场代码，可选，自动推断

        Returns:
            Dict 包含:
                - pre_market: 盘前数据列表
                - trading: 盘中数据列表
                - market_date: 市场日期
        """
        try:
            date_int = int(date)
        except (ValueError, TypeError):
            self.logger.error(f"Invalid date format: {date}, expected YYYYMMDD")
            return None

        return self._fetch_trend_raw(code, date=date_int, daycount=1, market=market, label=f"history {date}")

    def fetch_trend(self, code: str, date: Optional[str] = None, market: Optional[int] = None) -> Optional[Dict[str, List[Dict]]]:
        """获取分时数据（自动判断当日或历史）

        Args:
            code: 股票代码，支持 "600519", "SH600519" 等格式
            date: 日期，格式 "YYYYMMDD"，为None或"0"时获取当日数据
            market: 市场代码，可选，自动推断

        Returns:
            Dict 包含:
                - pre_market: 盘前数据列表
                - trading: 盘中数据列表
                - market_date: 市场日期
        """
        if date is None or date == "0":
            return self.fetch_intraday_trend(code, market=market)
        return self.fetch_history_trend(code, date, market=market)
