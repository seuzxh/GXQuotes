#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill 包内默认配置选择测试（不访问网络）。"""
import importlib.util
import os
from pathlib import Path

import yaml


_SCRIPT_PATH = Path(__file__).parents[1] / "skill" / "scripts" / "quotes.py"
_SPEC = importlib.util.spec_from_file_location("gxquotes_skill_runtime_config", _SCRIPT_PATH)
quotes = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(quotes)


def test_bundled_config_has_default_gateway():
    config_path = Path(quotes._BUNDLED_CONFIG)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base_url = config["api"]["base_url"]

    assert config_path.is_file()
    assert base_url.startswith(("http://", "https://"))


def test_bundled_config_is_temporary(monkeypatch):
    monkeypatch.delenv("KLINE_CONFIG_PATH", raising=False)

    with quotes._runtime_config():
        assert os.environ["KLINE_CONFIG_PATH"] == quotes._BUNDLED_CONFIG

    assert "KLINE_CONFIG_PATH" not in os.environ


def test_explicit_config_path_takes_precedence(monkeypatch):
    custom_path = "/runtime/admin/kline_config.yaml"
    monkeypatch.setenv("KLINE_CONFIG_PATH", custom_path)

    with quotes._runtime_config():
        assert os.environ["KLINE_CONFIG_PATH"] == custom_path

    assert os.environ["KLINE_CONFIG_PATH"] == custom_path
