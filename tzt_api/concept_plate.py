#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块相关请求：板块列表、板块K线、板块成份股、股票所属板块。

继承 KLineFetcher 获得 _request 等底座。概念板块方法既非纯日K也非纯分钟K，
独立成模块以便后续演进（如板块成份股分页、所属板块多策略解析等）。

单位口径（2026-08-24 实测标定，见 docs/concept_plate_api.md §5）：
  快照字段 price/change/high/low 原始为「万分之一」→ ÷1e6 换算为元/点；
  change_pct 原始为「千分之一」→ ÷1000 换算为 %。
  2026-08 前（v1.0.x）这些字段直接返回原始整数，v1.1.0 起统一换算。
"""

from typing import Dict, Iterator, List, Optional

from tzt_api._base import KLineFetcher

__all__ = ["ConceptPlateFetcher"]

# 10007 板块列表单页上限（超过报 ErrorNo=-2300 请求数量不能超过100，实测确认）
PLATE_LIST_PAGE_MAX = 100


class ConceptPlateFetcher(KLineFetcher):
    """概念板块数据获取客户端。

    提供中焯行情 API 的概念板块相关接口封装：
      - get_all_concept_plates：获取所有概念板块列表（自动翻页，全量）
      - get_concept_plate_kline：获取指定板块的日K线
      - get_concept_plate_min_kline：获取板块指数分钟K线（v2.0.0 新增，G6）
      - get_concept_plate_trend：获取板块指数分时（v2.0.0 新增，G6）
      - get_concept_plate_stocks：获取板块成份股（单页，含板块自身）
      - iter_concept_plate_stocks：生成器，自动翻页产出全部成份股（过滤板块自身）
      - get_stock_concept_plates：获取股票所属的概念板块

    使用示例:
        >>> fetcher = ConceptPlateFetcher()
        >>> plates = fetcher.get_all_concept_plates()
    """

    @staticmethod
    def _convert_ratio(raw: int) -> float:
        """比率类字段（千分之一）→ %（如 PxChgPct 原始 3297 → 3.297%）。"""
        return round(raw / 1000, 3)

    def _parse_quote_rows(self, raw: Dict, with_high_low: bool = False) -> List[Dict]:
        """解析列式快照响应（StockCode/StockName/MarketSN + 可选行情列），单位换算后返回行列表。"""
        if not ("StockCode" in raw and "StockName" in raw and "MarketSN" in raw):
            return []
        codes = raw["StockCode"]
        rows = []
        for i in range(len(codes)):
            row = {
                "code": codes[i],
                "name": raw["StockName"][i] if i < len(raw["StockName"]) else "",
                "market": raw["MarketSN"][i] if i < len(raw["MarketSN"]) else None,
            }
            if i < len(raw.get("QuoteLast") or []):
                row["price"] = self._convert_price(raw["QuoteLast"][i])
            if i < len(raw.get("PxChg") or []):
                row["change"] = self._convert_price(raw["PxChg"][i])
            if i < len(raw.get("PxChgPct") or []):
                row["change_pct"] = self._convert_ratio(raw["PxChgPct"][i])
            if with_high_low:
                if i < len(raw.get("High") or []):
                    row["high"] = self._convert_price(raw["High"][i])
                if i < len(raw.get("Low") or []):
                    row["low"] = self._convert_price(raw["Low"][i])
            rows.append(row)
        return rows

    def get_all_concept_plates(self, limit: Optional[int] = None, page_size: int = PLATE_LIST_PAGE_MAX) -> Optional[List[Dict]]:
        """获取所有概念板块列表（自动翻页全量）。

        v1.1.0 起按 ``start`` 翻页聚合全部板块（实测总数约 390，单页上限 100，
        共 4 页请求）；v1.0.x 仅返回按涨跌幅排序的前 30 条。

        参数:
            limit (int, optional): 最多返回的板块数，None 表示全量。
            page_size (int, optional): 每页请求条数（API 上限 100）。

        返回值:
            Optional[List[Dict]]: 概念板块列表，每项包含：
                - code (str): 板块代码
                - name (str): 板块名称
                - market (int): 市场代码（44 表示概念板块市场）
                - price (float, optional): 最新点位（点，已换算）
                - change (float, optional): 涨跌（点，已换算）
                - change_pct (float, optional): 涨跌幅（%，已换算）
            首页请求失败返回 None；翻页中途失败返回已获取部分（并告警）。
        """
        kline_cfg = self.config.get("kline", {})
        base_params = {
            "Action": 10007,
            "needtitle": 1,
            "subtype": 1,
            "rights": kline_cfg.get("rights", 0),
            "direction": 1,
            "906.props": "0|2|10|514",
            "count": min(page_size, PLATE_LIST_PAGE_MAX),
            "groups": "HQ_StockInfo|HQ_StockProp",
            "sort": 514,
            "props": "10|510|514|573|4|575|5|574|6|576|7|577|12|13|21|551|513|521|23|906|751|752|753|754|755|756|757|11",
            "market": 44,
            "Route": kline_cfg.get("route", 1),
        }

        plates: List[Dict] = []
        start = 0
        while True:
            page_params = dict(base_params)
            page_params["start"] = start
            raw = self._request(page_params)
            if raw is None:
                if not plates:
                    return None
                self.logger.warning(
                    f"Plate list pagination failed at start={start}; "
                    f"returning {len(plates)} plates collected so far"
                )
                break

            page_rows = self._parse_quote_rows(raw)
            if not page_rows:
                break
            plates.extend(page_rows)
            total = raw.get("max")
            self.logger.info(
                f"Fetched concept plates page: +{len(page_rows)}, total collected={len(plates)}, api max={total}"
            )

            start += len(page_rows)
            if len(page_rows) < page_params["count"]:
                break  # 短页 = 末页
            if total is not None and start >= int(total):
                break
            if limit is not None and len(plates) >= limit:
                break

        if limit is not None:
            plates = plates[:limit]
        self.logger.info(f"Fetched {len(plates)} concept plates in total")
        return plates

    def get_concept_plate_kline(self, plate_code: str, count: int = -220, market: int = 44) -> Optional[List[Dict]]:
        """获取指定概念板块的日K线数据。

        从API获取指定概念板块的历史日K线数据。默认获取最近220个交易日的数据。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            count (int, optional): K线数量，负值表示从最新数据向前获取。
                默认值为 -220。
            market (int, optional): 市场代码，44表示概念板块市场。默认值为 44。

        返回值:
            Optional[List[Dict]]: K线数据列表（字段与个股日K一致，单位已换算）。
            如果请求失败或无数据，返回 None。
        """
        klinetype = "500"
        kline_cfg = self.config.get("kline", {})
        params = {
            "Action": 10002,
            "code": plate_code,
            "market": market,
            "klinetype": klinetype,
            "cqType": 0,
            "props": kline_cfg.get("props", "0|1|2|3|4|191|190|519"),
            "422.daycount": -220,
            f"{klinetype}.count": count,
            "Route": kline_cfg.get("route", 1),
        }

        raw = self._request(params)
        items = self._extract_kline_list(raw, klinetype, label=f"plate_code={plate_code}")
        if items is None:
            return None
        return self._parse_kline_items(items, klinetype)

    def get_concept_plate_min_kline(self, plate_code: str, freq: str = "5min",
                                    count: Optional[int] = None, pages: int = 1) -> Optional[List[Dict]]:
        """获取板块指数分钟K线（v2.0.0 新增，G6；2026-08-24 实测 market=44 可用）。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            freq (str, optional): 分钟频率 1min/5min/15min/30min/60min，默认 "5min"。
            count (int, optional): K线数量，负值表示从最新数据向前获取（同个股分钟K）。
            pages (int, optional): locator 翻页页数，默认 1（语义同 fetch_min_kline）。

        返回值:
            Optional[List[Dict]]: 分钟K线列表，字段与个股分钟K一致
            （date/time/open/high/low/close/volume/amount，单位已换算）。
            请求失败或无数据返回 None。
        """
        return self._fetch_kline_series(plate_code, freq=freq, count=count,
                                        market=44, pages=pages)

    def get_concept_plate_trend(self, plate_code: str, date: Optional[str] = None) -> Optional[Dict]:
        """获取板块分时（v2.0.0 新增，G6；market=44，date=None 当日 / "YYYYMMDD" 历史）。"""
        date_int = 0 if date in (None, "0") else int(date)
        daycount = 0 if date_int == 0 else 1
        return self._fetch_trend_raw(plate_code, date=date_int, daycount=daycount,
                                     market=44, label=f"plate {plate_code}")

    def get_concept_plate_stocks(self, plate_code: str, start: int = 0, count: int = 10) -> Optional[List[Dict]]:
        """获取指定概念板块的成份股列表（单页，含板块自身）。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            start (int, optional): 分页起始位置，从 0 开始。默认值为 0。
            count (int, optional): 每页获取的股票数量。默认值为 10。

        返回值:
            Optional[List[Dict]]: 成份股列表，每个股票包含 code/name/market
            及可选的 price/change/change_pct/high/low（v1.1.0 起已换算：价格类
            为元、change_pct 为 %）。⚠️ 因固定 ``block.include=1``，**首项为
            板块自身**（market=44），其后才是成份股（见 docs/concept_plate_api.md §3.3）。
            请求失败返回 None。
        """
        kline_cfg = self.config.get("kline", {})
        params = {
            "Action": 10005,
            "block.include": 1,
            "block.type": 1,
            "needtitle": 1,
            "rights": kline_cfg.get("rights", 0),
            "block": plate_code,
            "direction": 1,
            "start": start,
            "count": count,
            "groups": "HQ_StockInfo|HQ_StockProp",
            "sort": 514,
            "props": "710|560|514|10|4|6|7|60|61|62|11|510|711",
            "Route": kline_cfg.get("route", 1),
            "routemarkets": 44,
        }

        raw = self._request(params)
        if raw is None:
            return None
        stocks = self._parse_quote_rows(raw, with_high_low=True)
        self.logger.info(f"Fetched {len(stocks)} stocks for plate {plate_code}")
        return stocks

    def iter_concept_plate_stocks(self, plate_code: str, page_size: int = PLATE_LIST_PAGE_MAX) -> Iterator[Dict]:
        """生成器：自动翻页产出板块**全部成份股**（过滤板块自身，v1.1.0 新增）。

        按 start/count 循环翻页直至短页；每页剔除 market=44 的板块自身行。
        全量约等于响应 ``max`` 字段减 1（板块自身）。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            page_size (int, optional): 每页请求条数，默认 100。

        Yields:
            Dict: 成份股行（同 get_concept_plate_stocks 的单行结构，单位已换算）。
        """
        start = 0
        while True:
            batch = self.get_concept_plate_stocks(plate_code, start=start, count=page_size)
            if not batch:
                return
            for stock in batch:
                if stock.get("market") == 44:
                    continue  # block.include=1 使首项为板块自身，剔除
                yield stock
            if len(batch) < page_size:
                return  # 短页 = 末页
            start += len(batch)

    # 股票所属板块的关联属性 ID（《行情3.0股票属性ID》v1.229）：
    #   900 = CoIndBlkIdx 隶属行业板块指数（仅 1 条）
    #   901 = CoBlkIdx 隶属版块指数（含行业/概念/地域/风格，可多条）
    #   923 = RegionBlkIdx 地域板块
    # 关联属性（val_type=8）须配 {propID}.props 指定关联证券的出参属性：0=代码 1=市场 2=名称
    STOCK_PLATE_PROPS = "900|901|923"
    PLATE_RESPONSE_KEYS = {
        "900": "CoIndBlkIdx",
        "901": "CoBlkIdx",
        "923": "RegionBlkIdx",
    }

    @staticmethod
    def _parse_plate_group(raw: Dict, key: str) -> List[Dict]:
        """解析 10000 响应中单个板块属性的关联证券列表。

        响应结构（outtype=1）: {key: [{"StockCode": [...], "StockName": [...], "MarketSN": [...]}]}
        """
        group = raw.get(key)
        if not group or not isinstance(group, list) or len(group) == 0:
            return []
        inner = group[0]
        if not isinstance(inner, dict):
            return []

        codes = inner.get("StockCode") or []
        names = inner.get("StockName") or []
        markets = inner.get("MarketSN") or []

        plates = []
        for i, plate_code in enumerate(codes):
            plate = {"code": plate_code}
            if i < len(names):
                plate["name"] = names[i]
            if i < len(markets):
                plate["market"] = markets[i]
            plates.append(plate)
        return plates

    def get_stock_concept_plates(self, code: str, market: Optional[int] = None, plate_type: Optional[str] = None) -> Optional[List[Dict]]:
        """获取指定股票所属的板块列表（官方属性 901 CoBlkIdx，2026-08 实测可用）。

        通过 Action=10000 请求关联属性 900（行业）/901（全部）/923（地域），
        用 900/923 的结果给 901 的板块标注类型。

        参数:
            code (str): 股票代码，例如 "600519"。裸码按指数优先规则推断市场，
                深市 000xxx 个股请用 "sz000001" 或显式传 market。
            market (int, optional): 市场代码，0深圳 1上海 103北京。默认自动推断。
            plate_type (str, optional): 板块类型过滤，可选 "industry"（行业）/
                "region"（地域）/"concept"（概念及风格）。默认 None 返回全部并带 type 字段。

        返回值:
            Optional[List[Dict]]: 板块列表，每项 {"code", "name", "market", "type"}。
            请求失败返回 None，无板块数据返回 []。
        """
        if market is None:
            market = self.infer_market(code)
        numeric_code = self._numeric_code(code)

        params = {
            "Action": 10000,
            "codes": f"{numeric_code}|{market}",
            "count": 1,
            "props": self.STOCK_PLATE_PROPS,
            "market": market,
            "outtype": 1,
        }
        for prop_id in self.STOCK_PLATE_PROPS.split("|"):
            params[f"{prop_id}.props"] = "0|1|2"

        raw = self._request(params)
        if raw is None:
            return None

        industry = self._parse_plate_group(raw, self.PLATE_RESPONSE_KEYS["900"])
        region = self._parse_plate_group(raw, self.PLATE_RESPONSE_KEYS["923"])
        all_plates = self._parse_plate_group(raw, self.PLATE_RESPONSE_KEYS["901"])
        if not all_plates:
            # CoBlkIdx 缺失时退化为行业+地域并集（正常沪深京股票不会走到这里）
            all_plates = industry + region

        industry_codes = {p["code"] for p in industry}
        region_codes = {p["code"] for p in region}
        for plate in all_plates:
            if plate["code"] in industry_codes:
                plate["type"] = "industry"
            elif plate["code"] in region_codes:
                plate["type"] = "region"
            else:
                plate["type"] = "concept"

        if plate_type is not None:
            plate_type = plate_type.lower()
            if plate_type not in ("industry", "region", "concept"):
                raise ValueError(f"无效的 plate_type: {plate_type}，可选值: industry, region, concept")
            all_plates = [p for p in all_plates if p["type"] == plate_type]

        self.logger.info(f"Fetched {len(all_plates)} plates for stock {code} (plate_type={plate_type})")
        return all_plates
