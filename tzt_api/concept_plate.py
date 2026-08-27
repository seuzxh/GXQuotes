#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块相关请求：行业/概念/地域/风格列表、板块K线、成份股、股票所属板块。

继承 KLineFetcher 获得 _request 等底座。板块方法既非纯日K也非纯分钟K，
独立成模块以便后续演进（如板块成份股分页、所属板块多策略解析等）。

单位口径（2026-08-24 实测标定，见 docs/concept_plate_api.md §5）：
  价格类原始为「万分之一」→ ÷1e6 换算为元/点；
  成交额原始为「万元」→ ÷1e4 换算为元；成交量类原始单位为股；
  百分比与量比类原始为「千分之一」→ ÷1000 换算为 %/倍。
  2026-08 前（v1.0.x）这些字段直接返回原始整数，v1.1.0 起统一换算。
"""

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence

from tzt_api._base import KLineFetcher
from tzt_api.quote_fields import QUOTE_FIELD_REGISTRY, SORT_DIRECTIONS

__all__ = [
    "PLATE_MARKET",
    "PLATE_LIST_PROPS",
    "MEMBER_LIST_PROPS",
    "MEMBER_SORT_FIELDS",
    "PLATE_SORT_DIRECTIONS",
    "PLATE_SORT_FIELDS",
    "PlateSortField",
    "PLATE_TYPE_TO_SUBTYPE",
    "PLATE_TYPE_ORDER",
    "ConceptPlateFetcher",
]

# 10007 板块列表单页上限（超过报 ErrorNo=-2300 请求数量不能超过100，实测确认）
PLATE_LIST_PAGE_MAX = 100
PLATE_MARKET = 44
PLATE_TYPE_TO_SUBTYPE = {
    "industry": 0,
    "concept": 1,
    "region": 2,
    "style": 3,
}
PLATE_TYPE_ORDER = tuple(PLATE_TYPE_TO_SUBTYPE)

# 10007 请求的现有 props 顺序保持不变；906 仅保留为原有返回字段。
PLATE_LIST_PROPS = (
    10, 510, 514, 573, 4, 575, 5, 574, 6, 576, 7, 577, 12, 13, 21,
    551, 513, 521, 23, 906, 751, 752, 753, 754, 755, 756, 757, 11,
)

# 10005 成份股快照字段：保留 GXAPP 6.3.4 真实请求顺序，但移除未消费且
# 体量很大的 43=TrendOp 完整盘中分时数组。560=连板字符串、60/61/62=板块
# 涨跌平家数、189=交易分钟数也不适合作为数值排行，MEMBER_SORT_FIELDS 只取标量字段。
MEMBER_LIST_PROPS = (
    560, 10, 510, 514, 573, 4, 575, 5, 574, 6, 576, 7, 577,
    12, 13, 21, 551, 513, 521, 23, 751, 752, 753, 754, 755, 756,
    757, 60, 61, 62, 11, 189,
)


@dataclass(frozen=True)
class PlateSortField:
    """10007 普通标量排序字段的稳定公共定义。"""

    prop_id: int
    raw_key: str
    label: str
    unit: str
    value_type: str


# 由普通行情字段注册表投影出板块语境标签/单位；保留既有类型与常量名兼容。
_PLATE_FIELD_NAMES = tuple(name for name in QUOTE_FIELD_REGISTRY if name not in {
    "order_ratio", "order_diff", "outside_volume",
})
PLATE_SORT_FIELDS = {
    name: PlateSortField(
        field.prop_id,
        field.raw_key,
        field.plate_label or field.label,
        field.plate_unit or field.stock_unit,
        field.value_type,
    )
    for name in _PLATE_FIELD_NAMES
    for field in (QUOTE_FIELD_REGISTRY[name],)
}

PLATE_SORT_DIRECTIONS = SORT_DIRECTIONS

# 10005 与 10007 共享同一套 27 个普通数值行情属性和稳定英文键。
# 使用派生注册表避免协议 ID、单位换算在两个接口中出现双重事实源。
MEMBER_SORT_FIELDS = {
    name: field
    for name, field in PLATE_SORT_FIELDS.items()
    if field.prop_id in MEMBER_LIST_PROPS
}


class ConceptPlateFetcher(KLineFetcher):
    """概念板块数据获取客户端。

    提供中焯行情 API 的概念板块相关接口封装：
      - get_all_plates：按行业/概念/地域/风格获取板块列表（自动翻页）
      - get_all_concept_plates：get_all_plates("concept") 的兼容入口
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

    def _convert_plate_sort_field(self, raw, field: PlateSortField):
        """按 tztZFPropField 的值类型将排序字段换算为对外单位。"""
        if raw is None:
            return None
        if field.value_type == "price":
            return self._convert_price(raw)
        if field.value_type == "amount":
            return self._convert_turnover(raw)
        if field.value_type == "volume":
            return self._convert_volume(raw)
        if field.value_type in ("percentage", "ratio"):
            return self._convert_ratio(raw)
        raise ValueError(f"未知板块排序值类型: {field.value_type}")

    def _get_plate_field_value(self, raw: Dict, index: int,
                               field: PlateSortField):
        """安全读取并换算一项列式板块字段，返回 ``(是否存在, 值)``。"""
        values = raw.get(field.raw_key)
        if not isinstance(values, list) or index >= len(values):
            return False, None
        value = values[index]
        if value is None:
            return True, None
        try:
            return True, self._convert_plate_sort_field(value, field)
        except (TypeError, ValueError) as exc:
            self.logger.warning(
                "Invalid plate field %s at row %s: %r (%s)",
                field.raw_key, index, value, exc,
            )
            return True, None

    def _parse_quote_rows(self, raw: Dict, with_high_low: bool = False,
                          include_all_plate_fields: bool = False,
                          additional_fields: Optional[Sequence[str]] = None) -> List[Dict]:
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
            if include_all_plate_fields:
                # 10007 固定返回全部 27 个普通标量字段；缺列/短列/空值统一为 None，
                # 使库和 Skill 的 JSON schema 在不同板块及交易时段保持稳定。
                for output_name, field in PLATE_SORT_FIELDS.items():
                    present, value = self._get_plate_field_value(raw, i, field)
                    row[output_name] = value if present else None
            else:
                # 成份股等既有调用继续保持紧凑、可选字段的兼容结构。
                output_names = ["price", "change", "change_pct"]
                if with_high_low:
                    output_names.extend(("high", "low"))
                required_fields = set(additional_fields or ())
                output_names.extend(required_fields)
                for output_name in dict.fromkeys(output_names):
                    field = PLATE_SORT_FIELDS[output_name]
                    present, value = self._get_plate_field_value(raw, i, field)
                    if present or output_name in required_fields:
                        row[output_name] = value if present else None
            rows.append(row)
        return rows

    def get_all_plates(self, plate_type: str = "concept", limit: Optional[int] = None,
                       page_size: int = PLATE_LIST_PAGE_MAX, *,
                       sort_by: str = "change_pct",
                       direction: str = "desc") -> Optional[List[Dict]]:
        """获取沪深指定类型的板块列表（Action=10007，自动翻页）。

        ``plate_type`` 映射：industry=0 / concept=1 / region=2 / style=3；
        市场固定为 44。``sort_by`` 使用 ``PLATE_SORT_FIELDS`` 中的稳定英文键，
        ``direction`` 支持 asc/desc。按 ``start`` 翻页，单页上限 100。

        参数:
            plate_type (str): industry/concept/region/style，默认 concept。
            limit (int, optional): 最多返回的板块数，必须为正整数；None 表示全量。
            page_size (int, optional): 每页请求条数（API 上限 100）。
            sort_by (str, keyword-only): 排序字段，默认 change_pct。
            direction (str, keyword-only): asc 升序 / desc 降序，默认 desc。

        返回值:
            Optional[List[Dict]]: 板块列表，每项包含：
                - code (str): 板块代码
                - name (str): 板块名称
                - market (int): 市场代码（44 表示沪深板块市场）
                - ``PLATE_SORT_FIELDS`` 定义的 27 个普通标量字段（已换算）
                  缺失值为 None；906 关联列表不解析、不返回
            非 strict 模式下首页请求失败返回 None；翻页中途失败返回已获取部分。
            strict=True 时请求失败抛 TZTError，避免把部分结果误认为全量。
        """
        if not isinstance(plate_type, str):
            raise ValueError("plate_type 必须是 industry/concept/region/style")
        plate_type = plate_type.lower().strip()
        if plate_type not in PLATE_TYPE_TO_SUBTYPE:
            choices = ", ".join(PLATE_TYPE_ORDER)
            raise ValueError(f"无效的 plate_type: {plate_type}，可选值: {choices}")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= PLATE_LIST_PAGE_MAX:
            raise ValueError(f"page_size 必须是 1 到 {PLATE_LIST_PAGE_MAX} 之间的整数")
        if limit is not None:
            if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
                raise ValueError("limit 必须是正整数或 None")
        if not isinstance(sort_by, str):
            raise ValueError("sort_by 必须是排序字段的英文键")
        sort_by = sort_by.lower().strip()
        if sort_by not in PLATE_SORT_FIELDS:
            choices = ", ".join(PLATE_SORT_FIELDS)
            raise ValueError(f"无效的 sort_by: {sort_by}，可选值: {choices}")
        if not isinstance(direction, str):
            raise ValueError("direction 必须是 asc 或 desc")
        direction = direction.lower().strip()
        if direction not in PLATE_SORT_DIRECTIONS:
            raise ValueError(f"无效的 direction: {direction}，可选值: asc, desc")
        sort_field = PLATE_SORT_FIELDS[sort_by]

        kline_cfg = self.config.get("kline", {})
        base_params = {
            "Action": 10007,
            "needtitle": 1,
            "subtype": PLATE_TYPE_TO_SUBTYPE[plate_type],
            "rights": kline_cfg.get("rights", 0),
            "direction": PLATE_SORT_DIRECTIONS[direction],
            "906.props": "0|1|2|10|514",
            "count": page_size,
            "groups": "HQ_StockInfo|HQ_StockProp",
            "sort": sort_field.prop_id,
            "props": "|".join(str(prop_id) for prop_id in PLATE_LIST_PROPS),
            "market": PLATE_MARKET,
            "Route": kline_cfg.get("route", 1),
        }

        plates: List[Dict] = []
        start = 0
        while True:
            page_params = dict(base_params)
            page_params["start"] = start
            if limit is not None:
                page_params["count"] = min(page_size, limit - len(plates))
            raw = self._request(page_params)
            if raw is None:
                if not plates:
                    return None
                self.logger.warning(
                    f"{plate_type} plate pagination failed at start={start}; "
                    f"returning {len(plates)} plates collected so far"
                )
                break

            page_rows = self._parse_quote_rows(
                raw,
                include_all_plate_fields=True,
            )
            if not page_rows:
                break
            plates.extend(page_rows)
            total = raw.get("max")
            self.logger.info(
                f"Fetched {plate_type} plates page: +{len(page_rows)}, "
                f"total collected={len(plates)}, api max={total}"
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
        self.logger.info(f"Fetched {len(plates)} {plate_type} plates in total")
        return plates

    def get_all_concept_plates(self, limit: Optional[int] = None,
                               page_size: int = PLATE_LIST_PAGE_MAX, *,
                               sort_by: str = "change_pct",
                               direction: str = "desc") -> Optional[List[Dict]]:
        """兼容入口：获取全部沪深概念板块（等价于 get_all_plates("concept")）。"""
        return self.get_all_plates(
            "concept",
            limit=limit,
            page_size=page_size,
            sort_by=sort_by,
            direction=direction,
        )

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

    def get_concept_plate_stocks(self, plate_code: str, start: int = 0,
                                 count: int = 10, *,
                                 sort_by: str = "change_pct",
                                 direction: str = "desc") -> Optional[List[Dict]]:
        """获取指定概念板块的成份股列表（单页，含板块自身）。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            start (int, optional): 分页起始位置，从 0 开始。默认值为 0。
            count (int, optional): 每页获取的股票数量。默认值为 10。
            sort_by (str, keyword-only): 排序字段，使用 MEMBER_SORT_FIELDS 的
                稳定英文键，默认 change_pct。
            direction (str, keyword-only): asc 升序 / desc 降序，默认 desc。

        返回值:
            Optional[List[Dict]]: 成份股列表，每个股票包含 code/name/market
            及可选的 price/change/change_pct/high/low（v1.1.0 起已换算：价格类
            为元、change_pct 为 %）；若排序字段不在基础字段中，会追加对应的
            已换算具名字段，不返回 ``sort_value``。⚠️ 因固定 ``block.include=1``，**首项为
            板块自身**（market=44），其后才是成份股（见 docs/concept_plate_api.md §3.3）。
            请求失败返回 None。
        """
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise ValueError("start 必须是非负整数")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= PLATE_LIST_PAGE_MAX:
            raise ValueError(f"count 必须是 1 到 {PLATE_LIST_PAGE_MAX} 之间的整数")
        if not isinstance(sort_by, str):
            raise ValueError("sort_by 必须是排序字段的英文键")
        sort_by = sort_by.lower().strip()
        if sort_by not in MEMBER_SORT_FIELDS:
            choices = ", ".join(MEMBER_SORT_FIELDS)
            raise ValueError(f"无效的 sort_by: {sort_by}，可选值: {choices}")
        if not isinstance(direction, str):
            raise ValueError("direction 必须是 asc 或 desc")
        direction = direction.lower().strip()
        if direction not in PLATE_SORT_DIRECTIONS:
            raise ValueError(f"无效的 direction: {direction}，可选值: asc, desc")
        sort_field = MEMBER_SORT_FIELDS[sort_by]

        kline_cfg = self.config.get("kline", {})
        params = {
            "Action": 10005,
            "block.include": 1,
            "block.type": 1,
            "needtitle": 1,
            "rights": kline_cfg.get("rights", 0),
            "block": plate_code,
            "direction": PLATE_SORT_DIRECTIONS[direction],
            "start": start,
            "count": count,
            "groups": "HQ_StockInfo|HQ_StockProp",
            "sort": sort_field.prop_id,
            "props": "|".join(str(prop_id) for prop_id in MEMBER_LIST_PROPS),
            "Route": kline_cfg.get("route", 1),
            "routemarkets": 44,
        }

        raw = self._request(params)
        if raw is None:
            return None
        stocks = self._parse_quote_rows(
            raw,
            with_high_low=True,
            additional_fields=(sort_by,),
        )
        self.logger.info(f"Fetched {len(stocks)} stocks for plate {plate_code}")
        return stocks

    def iter_concept_plate_stocks(self, plate_code: str,
                                  page_size: int = PLATE_LIST_PAGE_MAX, *,
                                  sort_by: str = "change_pct",
                                  direction: str = "desc") -> Iterator[Dict]:
        """生成器：自动翻页产出板块**全部成份股**（过滤板块自身，v1.1.0 新增）。

        按 start/count 循环翻页直至短页；每页剔除 market=44 的板块自身行。
        全量约等于响应 ``max`` 字段减 1（板块自身）。

        参数:
            plate_code (str): 概念板块代码，例如 "994612"
            page_size (int, optional): 每页请求条数，默认 100。
            sort_by (str, keyword-only): 排序字段，默认 change_pct。
            direction (str, keyword-only): asc 升序 / desc 降序，默认 desc。

        Yields:
            Dict: 成份股行（同 get_concept_plate_stocks 的单行结构，单位已换算）。
        """
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= PLATE_LIST_PAGE_MAX:
            raise ValueError(f"page_size 必须是 1 到 {PLATE_LIST_PAGE_MAX} 之间的整数")
        start = 0
        while True:
            batch = self.get_concept_plate_stocks(
                plate_code,
                start=start,
                count=page_size,
                sort_by=sort_by,
                direction=direction,
            )
            if not batch:
                return
            member_rows = [
                stock for stock in batch
                if str(stock.get("market")) != str(PLATE_MARKET)
            ]
            for stock in member_rows:
                yield stock
            if len(member_rows) < page_size:
                return  # 短页 = 末页
            # block.include=1 会额外返回板块自身；start 只按真实成份股数推进。
            start += len(member_rows)

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
            code (str): 股票代码，例如 "600519"。按 v2 契约推断市场（显式前缀 >
                个股段位 > 抛异常），裸码 000xxx 歧义请用 "sz000001" 或显式传 market。
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
