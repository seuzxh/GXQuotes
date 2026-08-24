#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityResolver：标的意图路由（中焯搜索接口 10032，v2.0.0）。

输入标的词（6位代码/中文名/拼音首字母）→ 输出候选与路由结论（FR6）：
  unique    唯一候选（或 prefer 过滤后唯一 / 名称精确匹配）→ chosen
  ambiguous 多候选 → 上层向用户反问
  not_found 网关无结果（-200608/-206008）
  error     网络/网关异常
实测依据：docs/plans/2026-08-24-market-v2-and-routing-design.md §2（2026-08-24）。
"""
import logging
from typing import Dict, List, Optional

from tzt_api._transport import TZTClient, TZTAPIError

__all__ = ["SecurityResolver"]

_NOT_FOUND_NOS = {"-200608", "-206008"}


def _split(pipe: Optional[str]) -> List[str]:
    return [x for x in (pipe or "").rstrip("|").split("|") if x]


class SecurityResolver:
    """10032 意图路由器（Skill 层标的解析入口，只读 GET）。"""

    def __init__(self, config_path: Optional[str] = None):
        # 复用 KLineFetcher 的配置加载（限流/重试/地址解析一致）。
        # strict=False：-200608/-206008 等确定性失败返回 None 并记录 last_error，
        # 由 resolve() 折叠为 not_found/error 状态（路由层契约：永不抛出）。
        from tzt_api._base import KLineFetcher  # 局部导入避免模块环
        base = KLineFetcher(config_path=config_path, strict=False)
        self._client: TZTClient = base._client

    def resolve(self, term: str, prefer: Optional[str] = None) -> Dict:
        """解析标的词。prefer: "index"/"stock" 意图提示，用于多候选过滤。"""
        term = term.strip()
        params = ({"Action": 10032, "StockCodeList": term, "outtype": 1}
                  if term.isdigit()
                  else {"Action": 10032, "StockCode": term, "StockCount": 10,
                        "Account": 0, "outtype": 1})
        raw = self._client.request(params, accept_error_nos=("1", "2"))

        if raw is None:
            err = self._client.last_error
            if isinstance(err, TZTAPIError) and str(err.error_no) in _NOT_FOUND_NOS:
                return {"status": "not_found", "candidates": [], "chosen": None, "term": term}
            return {"status": "error", "candidates": [], "chosen": None,
                    "error": str(err) if err else "unknown", "term": term}

        codes = _split(raw.get("BinData"))
        labels = _split(raw.get("StockLabel"))
        markets = _split(raw.get("MarketNo"))
        candidates = []
        for i in range(0, len(codes) - 1, 2):
            j = i // 2
            candidates.append({
                "code": codes[i], "name": codes[i + 1],
                "market": int(markets[j]) if j < len(markets) else None,
                "label": labels[j] if j < len(labels) else "",
                "is_index": labels[j] == "指数" if j < len(labels) else False,
            })

        if not candidates:
            return {"status": "not_found", "candidates": [], "chosen": None, "term": term}

        exact = [c for c in candidates if c["name"] == term]
        pool = exact if exact else candidates
        if prefer in ("index", "stock"):
            filtered = [c for c in pool if c["is_index"] == (prefer == "index")]
            if len(filtered) == 1:
                pool = filtered
        if len(pool) == 1:
            return {"status": "unique", "candidates": candidates,
                    "chosen": pool[0], "term": term}
        return {"status": "ambiguous", "candidates": candidates, "chosen": None, "term": term}
