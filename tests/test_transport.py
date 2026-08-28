#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TZTClient 传输层单元测试（无需网络）。

覆盖：进程级共享限流（跨实例）、重试次数、类型化异常分类、
strict 模式、base_url 解析优先级、last_error 生命周期。
"""
import logging
import time

import pytest
import requests

from tzt_api import TZTClient, TZTConnectionError, TZTAPIError
from tzt_api._transport import TZTError


def make_client(api_cfg=None, strict=False):
    config = {"api": {
        "base_url": "http://test-gateway",
        "request_interval": 0.0, "max_retries": 3, "retry_delay": 0, "timeout": 1,
    }}
    if api_cfg:
        config["api"].update(api_cfg)
    return TZTClient(config, logging.getLogger("test"), strict=strict)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        outcome = self.outcomes.pop(0) if self.outcomes else {"ErrorNo": "0"}
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


# ============ 1. 进程级共享限流 ============

class TestSharedThrottle:
    def test_throttle_shared_across_instances(self):
        """两个 TZTClient 实例的连续 throttle 间隔应 ≥ request_interval（v1.1.0 核心修正）。"""
        TZTClient._last_request_time = 0.0  # 隔离：重置类级共享状态
        cfg = {"request_interval": 0.12}
        c1, c2 = make_client(cfg), make_client(cfg)

        start = time.time()
        c1.throttle()
        c2.throttle()
        elapsed = time.time() - start

        assert elapsed >= 0.10, f"跨实例请求间隔 {elapsed:.3f}s < 0.10s，限流未共享"
        TZTClient._last_request_time = 0.0  # 还原，避免拖慢后续测试

    def test_throttle_no_wait_when_idle(self):
        TZTClient._last_request_time = 0.0
        client = make_client({"request_interval": 5.0})
        start = time.time()
        client.throttle()  # 距上次请求已"很久"，不应等待
        assert time.time() - start < 0.5
        TZTClient._last_request_time = 0.0


# ============ 2. 请求 / 重试 / 异常 ============

class TestRequestRetries:
    def test_success_returns_result_and_clears_error(self):
        client = make_client()
        client.session = FakeSession([{"ErrorNo": "0", "Data": 42}])
        client.last_error = TZTError("previous failure")

        result = client.request({"Action": 10002})

        assert result == {"ErrorNo": "0", "Data": 42}
        assert client.last_error is None

    def test_network_error_retries_then_none(self):
        client = make_client()
        client.session = FakeSession([requests.ConnectionError("boom")] * 3)

        result = client.request({"Action": 10002})

        assert result is None
        assert len(client.session.calls) == 3  # max_retries=3
        assert isinstance(client.last_error, TZTConnectionError)

    def test_network_error_does_not_leak_gateway(self, caplog):
        secret_url = "http://secret-internal-gateway.example:7778"
        client = make_client({"base_url": secret_url})
        client.session = FakeSession([
            requests.ConnectionError(f"cannot connect to {secret_url}")
        ] * 3)

        with caplog.at_level(logging.WARNING):
            result = client.request({"Action": 10002})

        assert result is None
        assert secret_url not in str(client.last_error)
        assert secret_url not in caplog.text
        assert str(client.last_error) == "行情网关连接失败"

    def test_api_error_retries_then_none(self):
        client = make_client()
        client.session = FakeSession([{"ErrorNo": "-989903", "ErrorMessage": "未知功能"}] * 3)

        result = client.request({"Action": "aaa"})

        assert result is None
        assert isinstance(client.last_error, TZTAPIError)
        assert str(client.last_error.error_no) == "-989903"

    def test_api_error_recovers_on_retry(self):
        """前两次 API 错误、第三次成功 → 返回成功结果。"""
        client = make_client()
        client.session = FakeSession([
            {"ErrorNo": "-1", "ErrorMessage": "temp"},
            {"ErrorNo": "-1", "ErrorMessage": "temp"},
            {"ErrorNo": "0", "Data": 1},
        ])

        assert client.request({"Action": 1}) == {"ErrorNo": "0", "Data": 1}
        assert len(client.session.calls) == 3

    def test_strict_raises_typed_error(self):
        client = make_client(strict=True)
        client.session = FakeSession([{"ErrorNo": "-989903", "ErrorMessage": "未知功能"}] * 3)

        with pytest.raises(TZTAPIError):
            client.request({"Action": "aaa"})

    def test_strict_raises_connection_error(self):
        client = make_client(strict=True)
        client.session = FakeSession([requests.Timeout("slow")] * 3)

        with pytest.raises(TZTConnectionError):
            client.request({"Action": 10002})


# ============ 3. base_url 解析 ============

class TestBaseUrlResolution:
    def test_env_var_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("KLINE_API_BASE_URL", "http://from-env:1")
        client = make_client({"base_url": "http://from-config:2"})
        client.session = FakeSession([{"ErrorNo": "0"}])

        client.request({"Action": 1})

        assert client.session.calls[0]["url"].startswith("http://from-env:1")

    def test_config_used_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("KLINE_API_BASE_URL", raising=False)
        client = make_client({"base_url": "http://from-config:2"})
        client.session = FakeSession([{"ErrorNo": "0"}])

        client.request({"Action": 1})

        assert client.session.calls[0]["url"].startswith("http://from-config:2")

    def test_missing_base_url_raises_environment_error(self, monkeypatch):
        monkeypatch.delenv("KLINE_API_BASE_URL", raising=False)
        client = make_client({"base_url": ""})  # 显式清空配置

        with pytest.raises(EnvironmentError):
            client.request({"Action": 1})


# ============ 4. Fetcher 集成（委托保留 + strict 透传） ============

class TestFetcherTransportIntegration:
    def test_fetcher_delegates_request(self, monkeypatch):
        """_request 仍可被 monkeypatch（既有单测的拦截点，v1.1.0 保留）。"""
        from tzt_api import ConceptPlateFetcher

        fetcher = ConceptPlateFetcher()
        monkeypatch.setattr(fetcher, "_request", lambda params: {"stub": True})
        assert fetcher._request({"x": 1}) == {"stub": True}

    def test_fetcher_strict_propagates(self, monkeypatch):
        from tzt_api import KLineFetcher

        fetcher = KLineFetcher(strict=True)
        assert fetcher.strict is True
        assert fetcher._client.strict is True

    def test_fetcher_session_alias(self):
        from tzt_api import KLineFetcher

        fetcher = KLineFetcher()
        assert fetcher.session is fetcher._client.session

    def test_last_error_property(self):
        from tzt_api import KLineFetcher

        fetcher = KLineFetcher()
        assert fetcher.last_error is None


# ============ 5. 错误分类 + 状态码透传（M2 Task 3 / N2'） ============

class TestErrorClassification:
    """N2'：不可重试错误 fail-fast；10032 状态码可透传。"""

    def test_non_retryable_error_no_retry(self):
        """-2300（证券/参数错误）确定性失败：只调 1 次，无退避。"""
        client = make_client()
        client.session = FakeSession([{"ErrorNo": "-2300", "ErrorMessage": "证券代码错误"}] * 3)
        t0 = time.time()
        result = client.request({"Action": 10002})
        assert result is None
        assert len(client.session.calls) == 1          # ← 不重试
        assert time.time() - t0 < 0.5                  # ← 无退避等待
        assert isinstance(client.last_error, TZTAPIError)

    def test_non_retryable_strict_raises_fast(self):
        client = make_client(strict=True)
        client.session = FakeSession([{"ErrorNo": "-989903", "ErrorMessage": "未知功能"}])
        with pytest.raises(TZTAPIError):
            client.request({"Action": "aaa"})

    def test_accept_error_nos_passthrough(self):
        """10032 的 ErrorNo=1/2 是结果状态码：accept_error_nos 声明后按成功返回。"""
        client = make_client()
        payload = {"ErrorNo": "2", "ErrorMessage": "多条", "BinData": "000001|平安银行|"}
        client.session = FakeSession([payload])
        result = client.request({"Action": 10032}, accept_error_nos=("1", "2"))
        assert result == payload
        assert client.last_error is None
        assert len(client.session.calls) == 1

    def test_not_found_error_is_non_retryable(self):
        """搜索无结果（-200608/-206008）确定性失败：不重试，last_error 带 ErrorNo。"""
        client = make_client()
        client.session = FakeSession([{"ErrorNo": "-200608", "ErrorMessage": "无结果"}] * 3)
        assert client.request({"Action": 10032}) is None
        assert len(client.session.calls) == 1
        assert str(client.last_error.error_no) == "-200608"

    def test_retryable_error_still_retries(self):
        """网络错误仍按 max_retries 重试（回归保护）。"""
        client = make_client()
        client.session = FakeSession([requests.ConnectionError("x")] * 3)
        assert client.request({"Action": 10002}) is None
        assert len(client.session.calls) == 3
