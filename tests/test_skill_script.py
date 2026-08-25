#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行情 Skill 脚本冒烟（integration）：子进程运行，断言退出码与 JSON 结构。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).parents[1] / "skill" / "scripts" / "quotes.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


class TestSkillScript:
    def test_dayk_explicit_prefix(self):
        p = run("dayk", "sh600519", "--count", "-3", "--adjust", "none")
        assert p.returncode == 0
        data = json.loads(p.stdout)["data"]
        assert len(data) == 3 and data[-1]["close"] > 0

    def test_dayk_bare_ambiguous_exit3_with_candidates(self):
        p = run("dayk", "000001", "--count", "-1")
        assert p.returncode == 3
        assert len(json.loads(p.stdout)["candidates"]) == 2   # 平安银行 + 上证指数

    def test_resolve_not_found_exit2(self):
        assert run("resolve", "zzzzzz9999").returncode == 2

    def test_trend_intraday(self):
        p = run("trend", "sh600519")
        assert p.returncode == 0 and "trading" in json.loads(p.stdout)["data"]

    def test_plate_list_all_types(self):
        p = run("plate-list", "--type", "all", "--limit", "2")
        assert p.returncode == 0
        payload = json.loads(p.stdout)
        assert payload["meta"]["count"] == 8
        assert payload["meta"]["counts"] == {
            "industry": 2,
            "concept": 2,
            "region": 2,
            "style": 2,
        }
        assert {row["type"] for row in payload["data"]} == {
            "industry", "concept", "region", "style",
        }

    def test_plate_list_custom_sort(self):
        p = run(
            "plate-list", "--type", "concept", "--sort", "amount",
            "--direction", "desc", "--limit", "3",
        )
        assert p.returncode == 0
        payload = json.loads(p.stdout)
        assert payload["meta"]["sort"] == {"field": "amount", "direction": "desc"}
        values = [row["amount"] for row in payload["data"]]
        assert values == sorted(values, reverse=True)
        assert all("sort_value" not in row for row in payload["data"])

    def test_members_custom_sort_and_limit(self):
        p = run(
            "members", "994612", "--sort", "amount",
            "--direction", "desc", "--limit", "3",
        )
        assert p.returncode == 0
        payload = json.loads(p.stdout)
        assert payload["meta"]["plate"] == "994612"
        assert payload["meta"]["limit"] == 3
        assert payload["meta"]["sort"] == {"field": "amount", "direction": "desc"}
        assert len(payload["data"]) == 3
        values = [row["amount"] for row in payload["data"]]
        assert values == sorted(values, reverse=True)
        assert all(str(row["market"]) != "44" for row in payload["data"])
        assert all("sort_value" not in row for row in payload["data"])

    def test_plate_min_kline(self):
        p = run("platek", "994612", "--freq", "5min", "--count", "-3")
        assert p.returncode == 0 and len(json.loads(p.stdout)["data"]) > 0
