#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行情 Skill 执行入口：agent 经 SKILL.md 调用，stdout 输出 JSON。

退出码：0 成功 | 2 未找到标的（或网关无数据）| 3 歧义（stdout 打印候选）| 4 网关/配置/网络错误
子命令：
  resolve     <标的词> [--prefer index|stock]             标的解析（6位代码/中文名/拼音首字母）
  dayk        <代码> [--count N | --begin/--end] [--adjust qfq|hfq|none] [--factor]
  mink        <代码> --freq 1min|5min|15min|30min|60min [--count N] [--pages N]
  trend       <代码> [--date YYYYMMDD]                    分时（缺省当日）
  plate-list  [--type ...] [--sort FIELD] [--direction asc|desc] [--limit N | --full]
  plates      <代码> [--type concept|industry|region]     个股所属板块
  members     <板块代码> [--sort FIELD] [--direction asc|desc] [--limit N | --all]
  platek      <板块代码> [--freq ...]                     板块日K（缺省）/分钟K（给 --freq）
  platetrend  <板块代码> [--date YYYYMMDD]                板块分时（缺省当日）
  market-rank [--scope ...] [--sort FIELD] [--direction asc|desc] [--limit N]
                                                             京沪深市场个股排行
依赖：Release Skill 包自带 tzt-api v2.1.0；仓库开发态也可直接运行。需配置 KLINE_API_BASE_URL。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from itertools import islice

# Release 中的自包含依赖位于 scripts/vendor；仓库内开发时仍优先使用仓库源码。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_VENDOR_DIR = os.path.join(_SCRIPT_DIR, "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

# 仓库内直跑支持：skill/scripts/ → 仓库根（tzt_api 所在处）
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
if os.path.isdir(os.path.join(_REPO_ROOT, "tzt_api")) and _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from tzt_api import (
        AmbiguousCodeError,
        ConceptPlateFetcher,
        KLineFetcher,
        MarketResolutionError,
        MinKLineFetcher,
        MarketRankFetcher,
        SecurityResolver,
        TrendFetcher,
        TZTAPIError,
        TZTConnectionError,
        TZTError,
        UnknownCodeError,
    )
    from tzt_api.concept_plate import (
        PLATE_MARKET,
        MEMBER_SORT_FIELDS,
        PLATE_SORT_FIELDS,
        PLATE_TYPE_ORDER,
        PLATE_TYPE_TO_SUBTYPE,
    )
    from tzt_api.market import MARKET_TO_PREFIX
    from tzt_api.market_rank import (
        MARKET_RANK_PAGE_MAX,
        MARKET_RANK_SORT_FIELDS,
        MARKET_SCOPES,
    )
except ImportError:  # 环境缺依赖：给出可操作的指引而非 traceback
    print(json.dumps({"error": {
        "kind": "dependency",
        "message": "无法导入 tzt-api 库",
        "actionable": "请使用 Release 中的完整 skill 包，或在 GXQuotes 仓库内运行并先安装项目依赖",
    }}, ensure_ascii=False, indent=2))
    sys.exit(4)

# 退出码语义（与 SKILL.md 退出码表一致）
EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_AMBIGUOUS = 3
EXIT_ERROR = 4

AMBIGUOUS_HINT = "多个候选，请指定"
DAY_KLINE_DEFAULT_COUNT = -120   # 按需拉取：日K缺省约半年
MIN_KLINE_DEFAULT_COUNT = -240   # 按需拉取：分钟K缺省约一个交易日（1min 口径）
MEMBERS_DEFAULT_COUNT = 50       # members 缺省前 50 只（--all 全量）
PLATE_LIST_DEFAULT_LIMIT = 30    # plate-list 缺省每类最多 30 个（--full 全量）
MARKET_RANK_DEFAULT_LIMIT = 30   # market-rank 对齐真实 App 默认榜单条数

# 显式市场前缀（sh/sz/bj 后跟数字；个股与指数共用命名空间，v2 契约）
_EXPLICIT_PREFIX_RE = re.compile(r"^(?:sh|sz|bj)\d", re.IGNORECASE)


def _positive_int(value: str, option: str) -> int:
    """argparse 类型：只接受正整数，避免 Agent 无意产生无限/空查询。"""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option} 必须是正整数") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"{option} 必须是正整数")
    return parsed


def _bounded_positive_int(value: str, option: str, maximum: int) -> int:
    parsed = _positive_int(value, option)
    if parsed > maximum:
        raise argparse.ArgumentTypeError(f"{option} 不能超过 {maximum}")
    return parsed


def _nonnegative_int(value: str, option: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option} 必须是非负整数") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"{option} 必须是非负整数")
    return parsed


class _ScriptExit(Exception):
    """携带退出码终止脚本（emit_* 系列统一出口）。"""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


# ===== 输出契约（全部走 stdout，ensure_ascii=False + indent=2）=====

def _dump(payload: dict):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def emit_ok(data, meta=None):
    """成功：{"data": ..., "meta": {"count": N}}，exit 0。"""
    if meta is None:
        if isinstance(data, list):
            meta = {"count": len(data)}
        elif isinstance(data, dict) and "trading" in data:
            meta = {"count": len(data.get("trading") or []),
                    "pre_market_count": len(data.get("pre_market") or [])}
        elif isinstance(data, dict):
            meta = {"count": 1}
        else:
            meta = {"count": 1 if data else 0}
    _dump({"data": data, "meta": meta})
    raise _ScriptExit(EXIT_OK)


def emit_ambiguous(candidates):
    """歧义：{"candidates": [...], "hint": "多个候选，请指定"}，exit 3。"""
    _dump({"candidates": candidates, "hint": AMBIGUOUS_HINT})
    raise _ScriptExit(EXIT_AMBIGUOUS)


def emit_error(kind, message, actionable=None, code=EXIT_ERROR):
    """错误：{"error": {"kind", "message", "actionable"}}，exit code。"""
    err = {"kind": kind, "message": message}
    if actionable:
        err["actionable"] = actionable
    _dump({"error": err})
    raise _ScriptExit(code)


# ===== 标的解析（显式前缀优先 / 裸码歧义自动复析反问 / 板块代码直传）=====

def _resolver_route(result: dict) -> dict:
    """把 SecurityResolver.resolve 的结果路由为输出；仅 unique 返回 chosen。"""
    status = result.get("status")
    if status == "unique":
        return result["chosen"]
    if status == "ambiguous":
        emit_ambiguous(result.get("candidates") or [])
    if status == "not_found":
        emit_error("not_found", f"未找到标的: {result.get('term', '')}",
                   actionable="请确认代码/名称/拼音后重试，可先用 resolve 子命令查询",
                   code=EXIT_NOT_FOUND)
    emit_error("resolver", f"标的解析失败: {result.get('error', 'unknown')}",
               actionable="检查 KLINE_API_BASE_URL 与网络后重试")


def _run_for_code(code: str, fetch_fn, resolver: SecurityResolver):
    """执行 fetch_fn(code, market=None)；裸码 Ambiguous/Unknown 时经 resolver 复析。

    显式前缀（sh/sz/bj）直接调用不复析；裸码异常时自动复析：
    unique → 用 chosen 的 code+market（映射为显式前缀）重试一次；
    ambiguous → exit 3 打印候选；not_found → exit 2；error → exit 4。
    """
    try:
        return fetch_fn(code)
    except (AmbiguousCodeError, UnknownCodeError):
        if _EXPLICIT_PREFIX_RE.match(code):
            raise  # 显式前缀不应触发市场解析异常，防御性上抛（main 兜底 exit 4）
        chosen = _resolver_route(resolver.resolve(code))
        chosen_code = str(chosen.get("code", code))
        market = chosen.get("market")
        if market in MARKET_TO_PREFIX:
            retry_code, retry_market = MARKET_TO_PREFIX[market] + chosen_code, None
        else:
            retry_code, retry_market = chosen_code, market
        try:
            return fetch_fn(retry_code, market=retry_market)
        except (AmbiguousCodeError, UnknownCodeError) as e:
            emit_error("market", str(e),
                       actionable=f"resolver 候选 {chosen_code}(market={market}) 无法取数，"
                                  f"请用 sh/sz/bj 显式前缀重试")


def _require_data(data, label: str):
    """strict fetcher 下 None = 网关正常响应但无数据（如代码不存在），折叠为 exit 2。"""
    if data is None:
        emit_error("not_found", f"网关未返回{label}数据（代码可能不存在或该标的无此类行情）",
                   actionable="确认代码正确（指数/深市 000xxx 请带 sh/sz 前缀）后重试",
                   code=EXIT_NOT_FOUND)
    return data


# ===== 子命令实现 =====

def cmd_resolve(args):
    result = SecurityResolver().resolve(args.term, prefer=args.prefer)
    if result.get("status") == "unique":
        emit_ok({"term": result["term"], "status": "unique",
                 "chosen": result["chosen"], "candidates": result["candidates"]},
                meta={"count": len(result["candidates"]) or 1})
    _resolver_route(result)  # ambiguous / not_found / error → emit + 对应退出码


def cmd_dayk(args):
    kf, resolver = KLineFetcher(strict=True), SecurityResolver()
    use_range = args.begin is not None or args.end is not None
    count = None if use_range else (args.count if args.count is not None else DAY_KLINE_DEFAULT_COUNT)

    def fetch(code, market=None):
        if args.factor:
            return kf.fetch_day_kline_with_factor(code, count=count, market=market,
                                                  begindate=args.begin, enddate=args.end)
        return kf.fetch_day_kline(code, count=count, market=market,
                                  begindate=args.begin, enddate=args.end, adjust=args.adjust)

    emit_ok(_require_data(_run_for_code(args.code, fetch, resolver), "日K"))


def cmd_mink(args):
    mf, resolver = MinKLineFetcher(strict=True), SecurityResolver()
    count = args.count if args.count is not None else MIN_KLINE_DEFAULT_COUNT

    def fetch(code, market=None):
        return mf.fetch_min_kline(code, freq=args.freq, count=count, market=market, pages=args.pages)

    emit_ok(_require_data(_run_for_code(args.code, fetch, resolver), "分钟K"))


def cmd_trend(args):
    tf, resolver = TrendFetcher(strict=True), SecurityResolver()

    def fetch(code, market=None):
        return tf.fetch_trend(code, date=args.date, market=market)

    emit_ok(_require_data(_run_for_code(args.code, fetch, resolver), "分时"))


def cmd_plate_list(args):
    """获取行业/概念/地域/风格板块列表。

    ``all`` 按固定类型顺序串行请求，输出仍为扁平列表，每行补充
    ``type``，便于 Agent 后续筛选、排序和选取板块代码。
    """
    pf = ConceptPlateFetcher(strict=True)
    limit = None if args.full else args.limit
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if args.type != "all":
        data = _require_data(
            pf.get_all_plates(
                args.type,
                limit=limit,
                sort_by=args.sort,
                direction=args.direction,
            ),
            f"{args.type} 板块列表",
        )
        meta = {
            "count": len(data),
            "market": PLATE_MARKET,
            "type": args.type,
            "subtype": PLATE_TYPE_TO_SUBTYPE[args.type],
            "full": args.full,
            "sort": {"field": args.sort, "direction": args.direction},
            "retrieved_at": retrieved_at,
        }
        if not args.full:
            meta["limit"] = args.limit
        emit_ok(data, meta=meta)

    data = []
    counts = {}
    for plate_type in PLATE_TYPE_ORDER:
        rows = _require_data(
            pf.get_all_plates(
                plate_type,
                limit=limit,
                sort_by=args.sort,
                direction=args.direction,
            ),
            f"{plate_type} 板块列表",
        )
        counts[plate_type] = len(rows)
        data.extend({**row, "type": plate_type} for row in rows)

    meta = {
        "count": len(data),
        "market": PLATE_MARKET,
        "type": "all",
        "counts": counts,
        "subtypes": dict(PLATE_TYPE_TO_SUBTYPE),
        "full": args.full,
        "sort": {"field": args.sort, "direction": args.direction},
        "retrieved_at": retrieved_at,
    }
    if not args.full:
        meta["limit_per_type"] = args.limit
    emit_ok(data, meta=meta)


def cmd_plates(args):
    pf, resolver = ConceptPlateFetcher(strict=True), SecurityResolver()

    def fetch(code, market=None):
        return pf.get_stock_concept_plates(code, market=market, plate_type=args.type)

    emit_ok(_require_data(_run_for_code(args.code, fetch, resolver), "板块归属"))


def cmd_members(args):
    pf = ConceptPlateFetcher(strict=True)
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if args.all:
        data = list(pf.iter_concept_plate_stocks(
            args.plate,
            sort_by=args.sort,
            direction=args.direction,
        ))
    elif args.limit <= 100:
        # block.include=1 额外返回板块自身；count 本身仍表示成份股数量。
        rows = pf.get_concept_plate_stocks(
            args.plate,
            start=0,
            count=args.limit,
            sort_by=args.sort,
            direction=args.direction,
        ) or []
        data = [
            row for row in rows
            if str(row.get("market")) != str(PLATE_MARKET)
        ][:args.limit]
    else:
        # 10005 单页 count 上限 100；更大的有限排行使用同一排序口径分页并有界截取。
        data = list(islice(
            pf.iter_concept_plate_stocks(
                args.plate,
                sort_by=args.sort,
                direction=args.direction,
            ),
            args.limit,
        ))
    meta = {
        "count": len(data),
        "plate": args.plate,
        "full": args.all,
        "sort": {"field": args.sort, "direction": args.direction},
        "retrieved_at": retrieved_at,
    }
    if not args.all:
        meta["limit"] = args.limit
    emit_ok(data, meta=meta)


def cmd_platek(args):
    pf = ConceptPlateFetcher(strict=True)
    if args.freq:
        count = args.count if args.count is not None else MIN_KLINE_DEFAULT_COUNT
        data = pf.get_concept_plate_min_kline(args.plate, freq=args.freq,
                                              count=count, pages=args.pages)
        label = "板块分钟K"
    else:
        count = args.count if args.count is not None else DAY_KLINE_DEFAULT_COUNT
        data = pf.get_concept_plate_kline(args.plate, count=count)
        label = "板块日K"
    emit_ok(_require_data(data, label))


def cmd_platetrend(args):
    pf = ConceptPlateFetcher(strict=True)
    emit_ok(_require_data(pf.get_concept_plate_trend(args.plate, date=args.date), "板块分时"))


def cmd_market_rank(args):
    """获取指定市场范围的个股排行（Action=10006）。"""
    fetcher = MarketRankFetcher(strict=True)
    scope_key = args.scope.replace("-", "_")
    data = _require_data(
        fetcher.get_market_rank(
            scope_key,
            start=args.start,
            count=args.limit,
            sort_by=args.sort,
            direction=args.direction,
        ),
        f"{args.scope} 市场排行",
    )
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = dict(getattr(fetcher, "last_rank_meta", {}) or {})
    meta.update({
        "count": len(data),
        "scope": args.scope,
        "start": args.start,
        "limit": args.limit,
        "sort": {"field": args.sort, "direction": args.direction},
        "retrieved_at": retrieved_at,
    })
    emit_ok(data, meta=meta)


# ===== argparse =====

def build_parser():
    parser = argparse.ArgumentParser(
        prog="quotes.py",
        description="行情 Skill 执行入口（gxquotes）：stdout 输出 JSON，退出码 0/2/3/4。",
        epilog=("示例：python /absolute/path/to/gxquotes/scripts/quotes.py "
                "dayk sh600519 --count -3 --adjust none"))
    sub = parser.add_subparsers(dest="command", metavar="<子命令>", required=True)

    p = sub.add_parser("resolve", help="标的解析：6位代码/中文名/拼音首字母 → 候选与路由结论")
    p.add_argument("term", help="标的词，如 000300 / 贵州茅台 / 拼音缩写")
    p.add_argument("--prefer", choices=("index", "stock"), help="意图提示：多候选时仅保留指数/个股")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("dayk", help="日K线（--factor 附带复权因子）")
    p.add_argument("code", help="证券代码：sh600519 / sz000001 / 裸码（歧义自动复析）")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help=f"K线根数（负数=最近N根，默认 {DAY_KLINE_DEFAULT_COUNT}）")
    p.add_argument("--begin", metavar="YYYYMMDD", help="开始日期（与 --end 同用，优先于 --count）")
    p.add_argument("--end", metavar="YYYYMMDD", help="结束日期")
    p.add_argument("--adjust", choices=("qfq", "hfq", "none"),
                   help="复权方式（缺省沿用网关默认 cqtype）")
    p.add_argument("--factor", action="store_true",
                   help="附带复权因子（后复权÷不复权逐根计算；忽略 --adjust）")
    p.set_defaults(func=cmd_dayk)

    p = sub.add_parser("mink", help="分钟K线（1/5/15/30/60min）")
    p.add_argument("code", help="证券代码：sz399001 / sh600519 / 裸码（歧义自动复析）")
    p.add_argument("--freq", required=True,
                   choices=("1min", "5min", "15min", "30min", "60min"), help="分钟频率")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help=f"K线根数（默认 {MIN_KLINE_DEFAULT_COUNT}）")
    p.add_argument("--pages", type=int, default=1, help="locator 翻页页数（默认 1）")
    p.set_defaults(func=cmd_mink)

    p = sub.add_parser("trend", help="分时（当日/历史）")
    p.add_argument("code", help="证券代码：sh600519 / 裸码（歧义自动复析）")
    p.add_argument("--date", metavar="YYYYMMDD", help="历史日期（缺省当日）")
    p.set_defaults(func=cmd_trend)

    p = sub.add_parser("plate-list", help="行业/概念/地域/风格板块列表")
    p.add_argument(
        "--type",
        choices=(*PLATE_TYPE_ORDER, "all"),
        default="concept",
        help="板块类型（默认 concept；all 按固定顺序合并四类）",
    )
    p.add_argument(
        "--sort",
        choices=tuple(PLATE_SORT_FIELDS),
        default="change_pct",
        help="排序字段（默认 change_pct，完整含义见 SKILL.md 引用表）",
    )
    p.add_argument(
        "--direction",
        choices=("asc", "desc"),
        default="desc",
        help="升序 asc / 降序 desc（默认 desc）",
    )
    limit_group = p.add_mutually_exclusive_group()
    limit_group.add_argument(
        "--limit",
        type=lambda value: _positive_int(value, "limit"),
        default=PLATE_LIST_DEFAULT_LIMIT,
        metavar="N",
        help=f"最多返回 N 个（all 时为每类 N 个；默认 {PLATE_LIST_DEFAULT_LIMIT}）",
    )
    limit_group.add_argument("--full", action="store_true", help="自动翻页获取全量")
    p.set_defaults(func=cmd_plate_list)

    p = sub.add_parser("plates", help="个股所属概念/行业/地域板块")
    p.add_argument("code", help="证券代码：sh600519 / 裸码（歧义自动复析）")
    p.add_argument("--type", choices=("concept", "industry", "region"),
                   help="板块类型过滤（缺省返回全部并带 type 字段）")
    p.set_defaults(func=cmd_plates)

    p = sub.add_parser("members", help="板块成份股排行（默认涨幅降序前 50，--all 全量）")
    p.add_argument("plate", help="板块代码，如 994612（直传网关，不做标的解析）")
    p.add_argument(
        "--sort",
        choices=tuple(MEMBER_SORT_FIELDS),
        default="change_pct",
        help="排序字段（默认 change_pct，完整含义见 SKILL.md 引用表）",
    )
    p.add_argument(
        "--direction",
        choices=("asc", "desc"),
        default="desc",
        help="升序 asc / 降序 desc（默认 desc）",
    )
    member_limit_group = p.add_mutually_exclusive_group()
    member_limit_group.add_argument(
        "--limit",
        type=lambda value: _positive_int(value, "limit"),
        default=MEMBERS_DEFAULT_COUNT,
        metavar="N",
        help=f"最多返回 N 只（默认 {MEMBERS_DEFAULT_COUNT}）",
    )
    member_limit_group.add_argument(
        "--all",
        action="store_true",
        help="自动翻页拉取全部成份股",
    )
    p.set_defaults(func=cmd_members)

    p = sub.add_parser("platek", help="板块指数K线（缺省日K；给 --freq 则分钟K）")
    p.add_argument("plate", help="板块代码，如 994612（直传网关，不做标的解析）")
    p.add_argument("--freq", choices=("1min", "5min", "15min", "30min", "60min"),
                   help="给则为分钟K，缺省日K")
    p.add_argument("--count", type=int, default=None, metavar="N",
                   help=f"K线根数（默认 日K {DAY_KLINE_DEFAULT_COUNT} / 分钟K {MIN_KLINE_DEFAULT_COUNT}）")
    p.add_argument("--pages", type=int, default=1, help="分钟K翻页页数（默认 1）")
    p.set_defaults(func=cmd_platek)

    p = sub.add_parser("platetrend", help="板块指数分时（当日/历史）")
    p.add_argument("plate", help="板块代码，如 994612（直传网关，不做标的解析）")
    p.add_argument("--date", metavar="YYYYMMDD", help="历史日期（缺省当日）")
    p.set_defaults(func=cmd_platetrend)

    p = sub.add_parser("market-rank", help="京沪深市场个股排行（默认全A股涨幅降序前30）")
    p.add_argument(
        "--scope",
        choices=tuple(key.replace("_", "-") for key in MARKET_SCOPES),
        default="all-a",
        help="证券池：全A股/沪深A股/沪市/深市/北市/沪深主板/创业板",
    )
    p.add_argument(
        "--sort",
        choices=tuple(MARKET_RANK_SORT_FIELDS),
        default="change_pct",
        help="排序字段（默认 change_pct，完整含义见 Skill reference）",
    )
    p.add_argument(
        "--direction",
        choices=("asc", "desc"),
        default="desc",
        help="升序 asc / 降序 desc（默认 desc）",
    )
    p.add_argument(
        "--limit",
        type=lambda value: _bounded_positive_int(value, "limit", MARKET_RANK_PAGE_MAX),
        default=MARKET_RANK_DEFAULT_LIMIT,
        metavar="N",
        help=f"返回 N 只（1-{MARKET_RANK_PAGE_MAX}，默认 {MARKET_RANK_DEFAULT_LIMIT}）",
    )
    p.add_argument(
        "--start",
        type=lambda value: _nonnegative_int(value, "start"),
        default=0,
        metavar="N",
        help="排行起始偏移（默认 0）",
    )
    p.set_defaults(func=cmd_market_rank)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        try:
            args.func(args)
        except EnvironmentError as e:  # 库层未配置 KLINE_API_BASE_URL 时抛出（含原始指引）
            emit_error("config", f"行情网关地址未配置（KLINE_API_BASE_URL）: {e}",
                       actionable='请先 export KLINE_API_BASE_URL="http://<网关地址>"；'
                                  "若使用 YAML，请通过 KLINE_CONFIG_PATH 指向配置文件的绝对路径后重试")
        except TZTConnectionError as e:
            emit_error("network", str(e), actionable="检查网络连通性与 KLINE_API_BASE_URL 后重试")
        except TZTAPIError as e:
            emit_error("gateway", str(e), actionable="检查代码/参数后重试（ErrorNo 见 message）")
        except TZTError as e:
            emit_error("gateway", str(e))
        except MarketResolutionError as e:
            emit_error("market", str(e),
                       actionable="请使用 sh/sz/bj 显式前缀（如 sz000001 / sh000300 / bj899050）")
        return EXIT_OK
    except _ScriptExit as e:  # emit_* 的统一出口（成功/歧义/未找到/错误）
        return e.code


if __name__ == "__main__":
    sys.exit(main())
