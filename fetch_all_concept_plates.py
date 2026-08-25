#!/usr/bin/env python3
"""获取全部沪深行业/概念/地域/风格板块并输出 JSON。

数据来源为 ``ConceptPlateFetcher.get_all_plates``：内部调用中焯
Action=10007，固定查询 market=44，并自动按 start/count 翻页。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from tzt_api import ConceptPlateFetcher, TZTError
from tzt_api.concept_plate import (
    PLATE_MARKET,
    PLATE_SORT_FIELDS,
    PLATE_TYPE_ORDER,
    PLATE_TYPE_TO_SUBTYPE,
)


def _page_size(value: str) -> int:
    size = int(value)
    if not 1 <= size <= 100:
        raise argparse.ArgumentTypeError("page-size 必须在 1 到 100 之间")
    return size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="获取全部沪深行业/概念/地域/风格板块（market=44），输出 JSON。"
    )
    parser.add_argument(
        "--type",
        choices=(*PLATE_TYPE_ORDER, "all"),
        default="concept",
        help="板块类型（默认 concept；all 获取并合并四类）",
    )
    parser.add_argument(
        "--page-size",
        type=_page_size,
        default=100,
        help="每页请求数量，范围 1-100（默认 100）",
    )
    parser.add_argument(
        "--sort",
        choices=tuple(PLATE_SORT_FIELDS),
        default="change_pct",
        help="排序字段（默认 change_pct）",
    )
    parser.add_argument(
        "--direction",
        choices=("asc", "desc"),
        default="desc",
        help="升序 asc / 降序 desc（默认 desc）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出文件路径；不传时输出到 stdout",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="输出紧凑 JSON，而不是带缩进的 JSON",
    )
    return parser


def _json_text(payload: dict, compact: bool) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=None if compact else 2,
        allow_nan=False,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        # strict=True：任一分页请求失败就抛异常，避免把部分列表当成全量结果。
        fetcher = ConceptPlateFetcher(strict=True)
        retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if args.type == "all":
            plates = []
            counts = {}
            for plate_type in PLATE_TYPE_ORDER:
                rows = fetcher.get_all_plates(
                    plate_type,
                    page_size=args.page_size,
                    sort_by=args.sort,
                    direction=args.direction,
                )
                if rows is None:
                    raise RuntimeError(f"网关未返回 {plate_type} 板块数据")
                counts[plate_type] = len(rows)
                plates.extend({**row, "type": plate_type} for row in rows)
            meta = {
                "count": len(plates),
                "market": PLATE_MARKET,
                "type": "all",
                "counts": counts,
                "subtypes": dict(PLATE_TYPE_TO_SUBTYPE),
                "sort": {"field": args.sort, "direction": args.direction},
                "retrieved_at": retrieved_at,
            }
        else:
            plates = fetcher.get_all_plates(
                args.type,
                page_size=args.page_size,
                sort_by=args.sort,
                direction=args.direction,
            )
            if plates is None:
                raise RuntimeError(f"网关未返回 {args.type} 板块数据")
            meta = {
                "count": len(plates),
                "market": PLATE_MARKET,
                "type": args.type,
                "subtype": PLATE_TYPE_TO_SUBTYPE[args.type],
                "sort": {"field": args.sort, "direction": args.direction},
                "retrieved_at": retrieved_at,
            }

        payload = {"data": plates, "meta": meta}
        content = _json_text(payload, compact=args.compact) + "\n"

        if args.output is None:
            sys.stdout.write(content)
        else:
            output_path = args.output.expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            print(
                f"已写入 {len(plates)} 个 {args.type} 板块：{output_path}",
                file=sys.stderr,
            )
        return 0

    except EnvironmentError as exc:
        print(
            "未配置行情网关。请先设置环境变量 "
            f"KLINE_API_BASE_URL：{exc}",
            file=sys.stderr,
        )
    except TZTError as exc:
        print(f"获取板块失败：{exc}", file=sys.stderr)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"获取或保存板块失败：{exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
