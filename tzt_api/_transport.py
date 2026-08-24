#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享传输层：HTTP 会话、进程级限流、重试与类型化异常。

从 KLineFetcher 基类中抽取的传输职责（2026-08 架构优化）：
  - 会话复用与限流改为**进程级共享**——此前每个 Fetcher 实例独立限流，
    同进程混用多类 Fetcher（如行情 Skill 场景）时实际请求速率为配置的 N 倍
  - 失败语义：默认仍返回 None（向后兼容），但记录 ``last_error``；
    ``strict=True`` 时抛类型化异常（供 Skill 层错误自诊断）
  - base_url 解析顺序：环境变量 KLINE_API_BASE_URL > 配置 api.base_url，
    未配置时抛 EnvironmentError（与历史行为一致）

限流铁律（继承 tztapi-agent 约定）：对中焯网关请求间隔 ≥ request_interval（默认 0.1s）。
"""
import os
import threading
import time
from typing import Dict, Optional

import requests

__all__ = [
    "TZTError",
    "TZTConnectionError",
    "TZTAPIError",
    "TZTClient",
]


class TZTError(Exception):
    """中焯行情 API 错误基类。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TZTConnectionError(TZTError):
    """网络层失败：连接/超时/HTTP 状态异常/响应不可解析。"""


class TZTAPIError(TZTError):
    """网关业务错误：ErrorNo ≠ 0 或响应结构异常。"""

    def __init__(self, message: str, error_no=None):
        super().__init__(message)
        self.error_no = error_no


class TZTClient:
    """行情网关传输客户端（会话 + 限流 + 重试）。

    限流状态为**类级共享**：同一进程内所有 TZTClient / Fetcher 实例对网关的
    请求共同满足 request_interval 间隔（多实例不再各自计时）。
    """

    # 类级共享限流状态（跨实例、跨线程）
    _THROTTLE_LOCK = threading.Lock()
    _last_request_time = 0.0

    def __init__(self, config: Dict, logger, strict: bool = False):
        self.config = config
        self.logger = logger
        self.strict = strict
        self.session = requests.Session()
        self.last_error: Optional[TZTError] = None

    # ----- 限流 -----

    def throttle(self):
        """保证距上一次（任意实例发起的）请求至少间隔 request_interval。"""
        interval = self.config.get("api", {}).get("request_interval", 0.1)
        with self._THROTTLE_LOCK:
            elapsed = time.time() - self._last_request_time
            wait = interval - elapsed
            if wait > 0:
                time.sleep(wait)
            type(self)._last_request_time = time.time()

    # ----- 请求 -----

    def _resolve_base_url(self) -> str:
        base_url = os.environ.get("KLINE_API_BASE_URL") or self.config.get("api", {}).get("base_url", "")
        if not base_url:
            raise EnvironmentError(
                "API base URL is not configured. "
                "Set the KLINE_API_BASE_URL environment variable (e.g. in .env or as a GitHub Secret/Variable), "
                "or set api.base_url in your kline_config.yaml."
            )
        return base_url

    def request(self, params: Dict) -> Optional[Dict]:
        """GET {base_url}/reqxml，带限流与指数退避重试。

        默认重试穷尽后返回 None 并记录 ``self.last_error``；
        ``strict=True`` 时改为抛出该类型化异常。
        """
        base_url = self._resolve_base_url()
        timeout = self.config.get("api", {}).get("timeout", 10)
        max_retries = self.config.get("api", {}).get("max_retries", 3)
        retry_delay = self.config.get("api", {}).get("retry_delay", 1)

        for attempt in range(max_retries):
            self.throttle()
            try:
                resp = self.session.get(
                    f"{base_url}/reqxml",
                    params=params,
                    timeout=timeout,
                )
                resp.raise_for_status()
                result = resp.json()

                error_no = result.get("ErrorNo")
                if error_no and str(error_no) != "0":
                    error = TZTAPIError(
                        f"API error: {result.get('ErrorMessage', 'unknown')} (ErrorNo={error_no})",
                        error_no=error_no,
                    )
                    self.last_error = error
                    self.logger.warning(
                        f"{error.message} (attempt {attempt + 1})"
                    )
                    time.sleep(retry_delay * (2 ** attempt))
                    continue

                self.last_error = None
                return result

            except requests.exceptions.RequestException as e:
                self.last_error = TZTConnectionError(f"Request error: {e}")
                self.logger.warning(f"Request error: {e} (attempt {attempt + 1})")
                time.sleep(retry_delay * (2 ** attempt))
            except Exception as e:
                self.last_error = TZTAPIError(f"Parse error: {e}")
                self.logger.warning(f"Parse error: {e} (attempt {attempt + 1})")
                time.sleep(retry_delay * (2 ** attempt))

        self.logger.error(f"API request failed after {max_retries} retries: params={params}")
        if self.strict:
            raise self.last_error or TZTError("API request failed for unknown reason")
        return None
