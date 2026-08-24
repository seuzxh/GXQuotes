# 行情 Skill M2 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 落地 M2 里程碑——market.py v2 显式契约（发版 2.0.0）、传输层错误分类、板块分钟行情封装、SecurityResolver + 行情 Skill（agent skill 形态）。

**Architecture:** 库层先行：`market.py` 重写为零指数知识的段位规则 + 解析异常（破坏性，v2.0.0）；`TZTClient` 增加不可重试错误分类与 10032 状态码透传；板块分钟K/分时通过把分钟K与分时的私有实现上移基类实现 DRY 复用；`tzt_api/search.py` 新增 `SecurityResolver`（10032 意图路由）；最后 `skill/` 目录交付 SKILL.md + 脚本。

**Tech Stack:** Python ≥3.9，仅 requests + PyYAML；pytest（单元 + integration 双层）。

**依据文档:** [需求 v0.4](../requirements/行情Skill需求.md) · [设计存档 market-v2](2026-08-24-market-v2-and-routing-design.md)（段位实测证据 §1.4、路由协议 §2）

**全局验收（计划完成时必须全部成立）:**
- `pytest -q` 单测全过；`KLINE_API_BASE_URL=<地址> pytest -m integration` 集成全过
- `python -c "from tzt_api import KLineFetcher, MinKLineFetcher, ConceptPlateFetcher, TrendFetcher, AdjustType, TZTClient, SecurityResolver, AmbiguousCodeError, UnknownCodeError"` 无异常
- `tzt_api` 中 `grep -rn "INDEX_CODE_MAP\|is_index\|get_index_info"` 零命中
- 版本号 2.0.0，CHANGELOG 有 2.0.0 节（含破坏性变更说明与 kline-qlib 迁移指引）

---

### Task 1: market.py v2 —— 异常体系 + 段位规则

**Files:**
- Rewrite: `tzt_api/market.py`
- Rewrite: `tests/test_market.py`
- Modify: `tzt_api/__init__.py`（导出三个异常）

**Step 1: 重写失败测试 `tests/test_market.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""market.py v2 契约测试：段位规则（10032 实测标定）+ 解析异常。"""
import pytest

from tzt_api import AmbiguousCodeError, UnknownCodeError
from tzt_api.market import MARKET_CODE_MAP, MARKET_TO_PREFIX, numeric_code, infer_market


class TestNumericCode:
    def test_strips_prefixes(self):
        assert numeric_code("sh600519") == "600519"
        assert numeric_code("SZ000001") == "000001"
        assert numeric_code("bj830799") == "830799"

    def test_bare_passthrough(self):
        assert numeric_code("600519") == "600519"


class TestInferMarketExplicitPrefix:
    """显式前缀 > 一切（个股/指数通用，共用命名空间）。"""

    def test_prefixes(self):
        assert infer_market("sh600519") == 1
        assert infer_market("SH000300") == 1      # 指数走同一前缀命名空间
        assert infer_market("sz000001") == 0      # 平安银行
        assert infer_market("SZ399001") == 0      # 深证成指
        assert infer_market("bj899050") == 103    # 北证50
        assert infer_market("Bj830799") == 103


class TestInferMarketSegments:
    """裸码个股段位直判（2026-08-24 10032 全段实测标定）。"""

    @pytest.mark.parametrize("code", ["600000", "601318", "603259", "605499",
                                      "688981", "689009", "900948"])
    def test_sh_segments(self, code):
        assert infer_market(code) == 1            # 900=沪B（实测补入）

    @pytest.mark.parametrize("code", ["001979", "002594", "003816", "300750", "301269"])
    def test_sz_segments(self, code):
        assert infer_market(code) == 0

    @pytest.mark.parametrize("code", ["830799", "430047", "870357", "920002", "899050"])
    def test_bj_segments(self, code):
        assert infer_market(code) == 103          # 899050 北证50："8" 规则恰好覆盖


class TestAmbiguous:
    @pytest.mark.parametrize("code", ["000001", "000002", "000016", "000300", "000688",
                                      "000905", "000852", "000858", "000333", "000651"])
    def test_000_segment_raises(self, code):
        """000xxx 整段抛异常——实测 7/11 双候选，静态不可分。"""
        with pytest.raises(AmbiguousCodeError) as ei:
            infer_market(code)
        assert "sz" in str(ei.value) and "sh" in str(ei.value)  # 消息含行动指引


class TestUnknown:
    @pytest.mark.parametrize("code", ["200002", "932000", "930050", "123456", "5"])
    def test_unknown_raises(self, code):
        """未知段位 fail-fast（200 深B 网关无数据；93x 中证需显式前缀）。"""
        with pytest.raises(UnknownCodeError):
            infer_market(code)


class TestV2Removals:
    def test_whitelist_removed(self):
        """v2.0.0：指数白名单与指数优先判定全部删除。"""
        import tzt_api.market as m
        assert not hasattr(m, "INDEX_CODE_MAP")
        assert not hasattr(m, "INDEX_CODE_PREFIXES")
        assert not hasattr(m, "is_index")
        assert not hasattr(m, "get_index_info")


class TestTables:
    def test_maps_kept(self):
        assert MARKET_CODE_MAP == {"sh": 1, "sz": 0, "bj": 103}
        assert MARKET_TO_PREFIX == {1: "sh", 0: "sz", 103: "bj"}
```

**Step 2: 运行确认失败**

Run: `python -m pytest tests/test_market.py -q`
Expected: FAIL / ERROR（`AmbiguousCodeError` 不存在、旧规则下 000001 不抛异常）

**Step 3: 重写 `tzt_api/market.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""市场规则单一事实源（v2 显式契约）：段位规则纯函数 + 解析异常。

v2.0.0 契约（设计存档 2026-08-24-market-v2-and-routing-design.md）：
  - 前缀 = 市场声明，个股与指数共用 sh/sz/bj 命名空间（对齐 qlib SH000300）
  - 零指数知识：仅个股段位规则（2026-08-24 经 10032 全段实测标定）
  - 000xxx 裸码歧义（深市个股/沪市指数实测共存）→ AmbiguousCodeError
  - 未知段位 → UnknownCodeError（fail-fast，替换 v1 "默认深"）
v1 的 INDEX_CODE_MAP / is_index / get_index_info / 指数优先规则已删除（破坏性变更）。
被 tzt-api 与 kline-qlib 共享。零第三方依赖。
"""

__all__ = [
    "MarketResolutionError",
    "AmbiguousCodeError",
    "UnknownCodeError",
    "MARKET_CODE_MAP",
    "MARKET_TO_PREFIX",
    "numeric_code",
    "infer_market",
]

# 市场 → 中焯市场代码（sh=沪 1, sz=深 0, bj=北 103）
MARKET_CODE_MAP = {"sh": 1, "sz": 0, "bj": 103}

# 反查表：市场代码 → qlib 目录前缀（下游 converter 的 code_to_qlib_dir 使用）
MARKET_TO_PREFIX = {1: "sh", 0: "sz", 103: "bj"}

# 个股段位规则（前缀匹配，全部 10032 实测标定，见设计存档 §1.4）
SH_SEGMENTS = ("600", "601", "603", "605", "688", "689", "900")  # 900=沪B
SZ_SEGMENTS = ("001", "002", "003", "300", "301")
BJ_SEGMENTS = ("8", "4", "92")  # 覆盖 830/430/870/920/899（899 北证指数同市场）

# 歧义段：深市个股与沪市指数真实共存（实测 11 样本 7 双候选），静态不可分
AMBIGUOUS_SEGMENTS = ("000",)


class MarketResolutionError(ValueError):
    """标的代码无法解析为市场（v2 解析异常基类）。"""


class AmbiguousCodeError(MarketResolutionError):
    """歧义代码：000xxx 裸码在深市个股与沪市指数两个市场同时存在真实证券。"""


class UnknownCodeError(MarketResolutionError):
    """未知段位代码：v2 起 fail-fast，不再默认深市。"""


def numeric_code(code: str) -> str:
    """剥离 sh/sz/bj 显式前缀，返回纯数字代码。无前缀则原样返回。"""
    upper = code.upper()
    if upper[:2] in ("SH", "SZ", "BJ"):
        return code[2:]
    return code


def infer_market(code: str) -> int:
    """推断市场代码（v2 契约：显式前缀 > 个股段位 > 异常）。

    判断顺序：
      1. 显式前缀 sh/sz/bj → 对应市场（个股/指数通用）
      2. 个股段位：600/601/603/605/688/689/900→沪；001/002/003/300/301→深；
         8/4/92→北
      3. 000xxx → AmbiguousCodeError（消息含 sz/sh 行动指引）
      4. 其余 → UnknownCodeError

    ⚠️ v2 破坏性变更：指数裸码（含 399xxx/93xxxx/000xxx）不再推断，
    请用显式前缀（sz399001 / sh932000 / sh000300）或显式传 market。
    """
    upper = code.upper()
    if upper.startswith("SH"):
        return MARKET_CODE_MAP["sh"]
    if upper.startswith("SZ"):
        return MARKET_CODE_MAP["sz"]
    if upper.startswith("BJ"):
        return MARKET_CODE_MAP["bj"]

    numeric = numeric_code(code)
    if numeric.startswith(AMBIGUOUS_SEGMENTS):
        raise AmbiguousCodeError(
            f"{code} 为歧义代码（深市个股/沪市指数共存）："
            f"个股请用 sz{numeric}，指数请用 sh{numeric}，或显式传 market"
        )
    if numeric.startswith(SH_SEGMENTS):
        return MARKET_CODE_MAP["sh"]
    if numeric.startswith(SZ_SEGMENTS):
        return MARKET_CODE_MAP["sz"]
    if numeric.startswith(BJ_SEGMENTS):
        return MARKET_CODE_MAP["bj"]
    raise UnknownCodeError(
        f"{code} 属未知段位，无法推断市场；请使用 sh/sz/bj 前缀或显式传 market"
    )
```

**Step 4: 更新 `tzt_api/__init__.py` 导出**

```python
from tzt_api.market import (
    MarketResolutionError, AmbiguousCodeError, UnknownCodeError,
)
# __all__ 追加这三个名字；docstring 注明 v2.0.0
```

**Step 5: 跑测试**

Run: `python -m pytest tests/test_market.py -q`
Expected: 全部 PASS

**Step 6: Commit**

```bash
git add tzt_api/market.py tzt_api/__init__.py tests/test_market.py
git commit -m "refactor!: market v2——零指数知识段位规则 + Ambiguous/Unknown 异常（删白名单）"
```

**测试标准（Task 1 验收）:**
- `python -m pytest tests/test_market.py -q` → 全过（显式前缀 6 例、段位 17 例、歧义 10 例、未知 5 例、删除断言、映射表）
- `python -c "from tzt_api import AmbiguousCodeError, UnknownCodeError, MarketResolutionError"` 成功
- `python -c "from tzt_api.market import infer_market; infer_market('000001')"` 抛 `AmbiguousCodeError` 且消息同时含 "sz000001" 与 "sh000001"

---

### Task 2: KLineFetcher 与存量测试适配 v2 契约

**Files:**
- Modify: `tzt_api/_base.py`（删 `is_index`/`get_index_info` 静态方法及 market 导入）
- Modify: `tests/test_structure_api.py`、`tests/test_split_interfaces.py`
- Rewrite: `tests/test_indices_integration.py`（白名单参数化 → 显式前缀表）

**Step 1: 更新结构守护测试（先失败）**

`tests/test_structure_api.py` 中：
- `test_method_attribution`：基类应有列表去掉 `infer_market` 之外的指数方法断言；新增负断言：

```python
        for m in ["is_index", "get_index_info"]:
            assert not hasattr(KLineFetcher, m), f"v2 已删除 {m}"
```

- `test_v2_market_exports`（新增）：

```python
    def test_v2_market_exports(self):
        from tzt_api import MarketResolutionError, AmbiguousCodeError, UnknownCodeError
        from tzt_api.market import SH_SEGMENTS, SZ_SEGMENTS, BJ_SEGMENTS, AMBIGUOUS_SEGMENTS
        assert issubclass(AmbiguousCodeError, MarketResolutionError)
        assert issubclass(UnknownCodeError, MarketResolutionError)
        assert issubclass(MarketResolutionError, ValueError)
```

**Step 2: 运行确认失败**

Run: `python -m pytest tests/test_structure_api.py -q`
Expected: FAIL（`KLineFetcher.is_index` 仍存在、新导出缺失）

**Step 3: 修改 `tzt_api/_base.py`**

- 删除 `from tzt_api.market import (INDEX_CODE_MAP, INDEX_CODE_PREFIXES, get_index_info, is_index, ...)` 中的已删符号，仅保留 `MARKET_CODE_MAP, infer_market, numeric_code`
- 删除 `__all__` 中的 `"INDEX_CODE_MAP"`, `"INDEX_CODE_PREFIXES"`
- 删除两个静态方法：`is_index`、`get_index_info`（保留 `_numeric_code`、`infer_market`）

**Step 4: 适配 `tests/test_split_interfaces.py`**

- `test_infer_market_static`：`"000001" == 1` 断言替换为：

```python
        with pytest.raises(AmbiguousCodeError):
            KLineFetcher.infer_market("000001")
```

（文件头 `from tzt_api import KLineFetcher` 处补 `AmbiguousCodeError`、`import pytest` 已有）
- `test_infer_market_all_prefixes` 保留（全部为显式前缀与合法段位）

**Step 5: 重写 `tests/test_indices_integration.py`（白名单已删，改显式前缀表）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指数行情集成测试（v2：显式前缀形式，原白名单参数化已随 INDEX_CODE_MAP 删除）。"""
import pytest

pytestmark = pytest.mark.integration

from tzt_api import KLineFetcher, MinKLineFetcher, TrendFetcher, AmbiguousCodeError

# 显式前缀 × 市场 × 名称（v2 契约：指数一律显式前缀，与 qlib SH000300 同构）
EXPLICIT_INDICES = [
    ("sh000001", 1, "上证指数"), ("sh000010", 1, "上证180"), ("sh000016", 1, "上证50"),
    ("sh000300", 1, "沪深300"), ("sh000688", 1, "科创50"), ("sh000852", 1, "中证1000"),
    ("sh000903", 1, "中证100"), ("sh000905", 1, "中证500"), ("sh000906", 1, "中证800"),
    ("sh000922", 1, "中证红利"), ("sh932000", 1, "中证2000"),
    ("sz399001", 0, "深证成指"), ("sz399004", 0, "深证100"), ("sz399006", 0, "创业板指"),
    ("sz399102", 0, "创业板综"), ("sz399295", 0, "创业板50"), ("sz399303", 0, "国证2000"),
    ("sz399971", 0, "中证传媒"), ("sz399997", 0, "中证白酒"),
    ("bj899050", 103, "北证50"),
]


class TestExplicitIndexKline:
    @pytest.mark.parametrize("code,market,name", EXPLICIT_INDICES,
                             ids=[c[2] for c in EXPLICIT_INDICES])
    def test_day_kline(self, day_fetcher, code, market, name):
        data = day_fetcher.fetch_day_kline(code, count=-1, adjust="none")
        assert data is not None and len(data) > 0, f"{code} {name} 日K无数据"


class TestV2BareIndexCodes:
    def test_bare_000_raises_before_request(self, day_fetcher):
        """裸 000xxx 在参数构造期抛异常——不发请求即失败。"""
        with pytest.raises(AmbiguousCodeError):
            day_fetcher.fetch_day_kline("000300", count=-1)

    def test_bare_399_now_unknown(self, day_fetcher):
        """v2 破坏性示例：裸 399001 不再按深市指数推断。"""
        from tzt_api import UnknownCodeError
        with pytest.raises(UnknownCodeError):
            day_fetcher.fetch_day_kline("399001", count=-1)
```

**Step 6: 跑单元全量 + 集成（真实网关）**

Run: `python -m pytest -q`
Expected: 全过（conftest 共享 fixtures 已就位）

Run: `KLINE_API_BASE_URL=<地址> python -m pytest tests/test_indices_integration.py -m integration -q`
Expected: 全过

**Step 7: Commit**

```bash
git add tzt_api/_base.py tests/test_structure_api.py tests/test_split_interfaces.py tests/test_indices_integration.py
git commit -m "refactor!: Fetcher 适配 v2——删除 is_index/get_index_info，指数测试改显式前缀"
```

**测试标准（Task 2 验收）:**
- `python -m pytest -q` 全过；`grep -rn "is_index\|INDEX_CODE_MAP\|get_index_info" tzt_api/` 零命中
- 集成：20 个显式指数（含 sh932000 中证2000、bj899050 北证50）日K全部有数据
- `fetch_day_kline("000300")` 抛 `AmbiguousCodeError` 且**网关未收到请求**（日志无 Fetching 行——参数构造期失败）

---

### Task 3: TZTClient 错误分类 + 10032 状态码透传（N2'）

**Files:**
- Modify: `tzt_api/_transport.py`
- Modify: `tests/test_transport.py`（追加测试类）

**Step 1: 追加失败测试**

```python
# tests/test_transport.py 追加

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
```

**Step 2: 运行确认失败**

Run: `python -m pytest tests/test_transport.py::TestErrorClassification -q`
Expected: FAIL（calls==3 断言失败——当前会重试）

**Step 3: 修改 `tzt_api/_transport.py`**

```python
# 模块级常量（置于 TZTClient 类定义前）
# 确定性业务错误：重试不可能成功，fail-fast（2026-08-24 实测观察：
# -2300 证券/参数错误族、-989903 未知功能、-200608/-206008 搜索无结果）
NON_RETRYABLE_ERROR_NOS = {"-2300", "-989903", "-200608", "-206008"}
```

`request()` 签名与 ErrorNo 分支改为：

```python
    def request(self, params: Dict, accept_error_nos: tuple = ()) -> Optional[Dict]:
        """GET {base_url}/reqxml，带限流与指数退避重试。

        Args:
            accept_error_nos: 视为**结果状态码**的 ErrorNo 集合（如 10032 的
                1=命中/2=多条），命中时按成功返回原始响应，不重试不置 last_error。
        """
        ...
                error_no = result.get("ErrorNo")
                if error_no and str(error_no) != "0":
                    if str(error_no) in tuple(accept_error_nos):
                        self.last_error = None
                        return result          # 结果状态码透传（10032）
                    error = TZTAPIError(...)
                    self.last_error = error
                    if str(error_no) in NON_RETRYABLE_ERROR_NOS:
                        self.logger.warning(f"{error.message} (不可重试，fail-fast)")
                        if self.strict:
                            raise error
                        return None            # ← 不重试
                    self.logger.warning(f"{error.message} (attempt {attempt + 1})")
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
```

**Step 4: 跑 transport 全量**

Run: `python -m pytest tests/test_transport.py -q`
Expected: 全过（含既有 16 项回归）

**Step 5: Commit**

```bash
git add tzt_api/_transport.py tests/test_transport.py
git commit -m "feat: TZTClient 错误分类——不可重试 ErrorNo fail-fast + accept_error_nos 状态码透传"
```

**测试标准（Task 3 验收）:**
- 新增 5 项测试全过；既有 transport 16 项回归全过
- `-2300` 恰好 1 次调用且耗时 <0.5s（无退避）；`accept_error_nos=("1","2")` 下 ErrorNo=2 的响应原样返回且 `last_error is None`
- 真实网关抽查：`TZTClient.request({"Action": "aaa"})` 日志只出现 1 次 "不可重试"（此前为 3 次重试 + 7s 退避）

---

### Task 4: 板块分钟K —— 分钟K实现上移基类 + 板块薄封装（G6 上）

**Files:**
- Modify: `tzt_api/_base.py`（新增 `_fetch_kline_series`）
- Modify: `tzt_api/min_kline.py`（`fetch_min_kline` 改为委托）
- Modify: `tzt_api/concept_plate.py`（新增 `get_concept_plate_min_kline`）
- Modify: `tests/test_structure_api.py`（方法归属断言）
- Test: `tests/test_split_interfaces.py`（板块分钟单测）、`tests/test_concept_plates.py`（集成）

**Step 1: 结构守护先行（失败测试）**

`test_structure_api.py` 的 `test_method_attribution` 追加：

```python
        assert not hasattr(KLineFetcher, "get_concept_plate_min_kline")
        assert hasattr(ConceptPlateFetcher, "get_concept_plate_min_kline")
        assert hasattr(KLineFetcher, "_fetch_kline_series")   # 私有共享实现上移基类
```

Run: `python -m pytest tests/test_structure_api.py -q` → Expected: FAIL

**Step 2: 实现——`_base.py` 追加（从 min_kline.py 原样迁移实现体）**

```python
    # ===== 分钟K共享实现（MinKLineFetcher / ConceptPlateFetcher 复用）=====

    def _fetch_kline_series(self, code: str, freq: str, count=None, market=None,
                            pages: int = 1, adjust: str = None) -> Optional[List[Dict]]:
        """按 freq 获取K线序列（分钟频率 + locator 翻页 + 去重排序）。

        原 MinKLineFetcher.fetch_min_kline 实现体（v2.0.0 上移基类供板块复用）。
        """
        # —— 原 fetch_min_kline 方法体整体迁入，self.logger 文案不变 ——
```

`min_kline.py` 改为：

```python
    def fetch_min_kline(self, code, freq="1min", count=None, market=None, pages=1, adjust=None):
        """（委托 KLineFetcher._fetch_kline_series，签名与行为不变。）"""
        return self._fetch_kline_series(code, freq=freq, count=count, market=market,
                                        pages=pages, adjust=adjust)
```

**Step 3: `concept_plate.py` 追加板块薄封装**

```python
    def get_concept_plate_min_kline(self, plate_code: str, freq: str = "5min",
                                    count: Optional[int] = None, pages: int = 1) -> Optional[List[Dict]]:
        """获取板块指数分钟K线（v2.0.0 新增，G6；2026-08-24 实测 market=44 可用）。

        freq: 1min/5min/15min/30min/60min；其余参数语义同 MinKLineFetcher.fetch_min_kline。
        返回字段与个股分钟K一致（date/time/open/high/low/close/volume/amount，单位已换算）。
        """
        return self._fetch_kline_series(plate_code, freq=freq, count=count,
                                        market=44, pages=pages)
```

**Step 4: 单元测试（`test_split_interfaces.py` 板块类追加，先失败后实现亦可与 Step 1-3 同轮）**

```python
    def test_plate_min_kline_unit(self, monkeypatch):
        """板块分钟K走 market=44 通道（mock _request 断言参数）。"""
        from tzt_api import ConceptPlateFetcher
        fetcher = ConceptPlateFetcher()
        captured = {}
        def fake(params):
            captured.update(params)
            return {"Min5KLine": [[{"Time": 20260824150000, "OpenPrice": 1796000000,
                                    "HighPrice": 1800000000, "LowPrice": 1790000000,
                                    "ClosePrice": 1796130000, "PeriodVolume": 100,
                                    "PeriodTurnover": 200}]]}
        monkeypatch.setattr(fetcher, "_request", fake)
        data = fetcher.get_concept_plate_min_kline("994612", freq="5min", count=-3)
        assert captured["market"] == 44 and captured["klinetype"] == "502"
        assert data and data[-1]["close"] == 1796.13
```

**Step 5: 集成测试（`tests/test_concept_plates.py` 追加类）**

```python
class TestConceptPlateMinKline:
    """G6：板块分钟行情（2026-08-24 实测网关支持）。"""

    @pytest.mark.parametrize("freq", ["1min", "5min", "15min", "30min", "60min"])
    def test_min_kline_all_freqs(self, plate_fetcher, freq):
        data = plate_fetcher.get_concept_plate_min_kline(TEST_PLATE, freq=freq, count=-3)
        assert data is not None and len(data) > 0
        assert "time" in data[-1] and data[-1]["close"] > 0
```

**Step 6: 跑测试**

Run: `python -m pytest -q && KLINE_API_BASE_URL=<地址> python -m pytest tests/test_concept_plates.py -m integration -q`
Expected: 全过（含个股分钟K回归——委托后行为不变）

**Step 7: Commit**

```bash
git add tzt_api/_base.py tzt_api/min_kline.py tzt_api/concept_plate.py tests/
git commit -m "feat: 板块分钟K（G6）——分钟K实现上移基类 + ConceptPlateFetcher 薄封装"
```

**测试标准（Task 4 验收）:**
- 单测：market=44 与 klinetype=502 参数断言过；个股 `fetch_min_kline` 全部既有测试回归过（委托无行为变化）
- 集成：板块 1/5/15/30/60min 五档全部返回带 time 字段、close>0 的数据
- 结构守护：`KLineFetcher` 无 `get_concept_plate_min_kline`、有 `_fetch_kline_series`

---

### Task 5: 板块分时 —— 分时实现上移基类 + 板块薄封装（G6 下）

**Files:**
- Modify: `tzt_api/_base.py`（新增 `_fetch_trend_raw`，自 trend.py 迁移 `_fetch_trend` 实现体及两个解析函数调用）
- Modify: `tzt_api/trend.py`（`_fetch_trend` 改为委托 `_fetch_trend_raw`）
- Modify: `tzt_api/concept_plate.py`（新增 `get_concept_plate_trend`）
- Test: `tests/test_concept_plates.py`（集成）、`tests/test_trend_unit.py`（回归）

**Step 1: 集成失败测试（`test_concept_plates.py` 追加）**

```python
class TestConceptPlateTrend:
    def test_intraday_trend(self, plate_fetcher):
        """板块分时（当日）：pre_market + trading 两段（2026-08-24 实测 TrendOp 241 点）。"""
        data = plate_fetcher.get_concept_plate_trend(TEST_PLATE)
        assert data is not None
        assert "market_date" in data and "pre_market" in data and "trading" in data

    def test_history_trend(self, plate_fetcher):
        data = plate_fetcher.get_concept_plate_trend(TEST_PLATE, date="20260821")
        assert data is not None and data["trading"]
```

Run（integration）→ Expected: FAIL（方法不存在）

**Step 2: 实现**

- `_base.py`：新增 `_fetch_trend_raw(code, date, daycount, market=None, label="")`——**原 trend.py `_fetch_trend` 实现体整体迁入**（`_parse_call_trend`/`_parse_trend_op`/`_convert_trend_time` 一并迁为基类方法，trend.py 改为从基类继承使用）
- `trend.py`：`_fetch_trend` 与 `fetch_intraday_trend`/`fetch_history_trend`/`fetch_trend` 保留公开签名，内部委托 `self._fetch_trend_raw(...)`
- `concept_plate.py`：

```python
    def get_concept_plate_trend(self, plate_code: str, date: Optional[str] = None) -> Optional[Dict]:
        """获取板块分时（v2.0.0 新增，G6；market=44，date=None 当日 / "YYYYMMDD" 历史）。"""
        date_int = 0 if date in (None, "0") else int(date)
        daycount = 0 if date_int == 0 else 1
        return self._fetch_trend_raw(plate_code, date=date_int, daycount=daycount,
                                     market=44, label=f"plate {plate_code}")
```

**Step 3: 跑回归 + 集成**

Run: `python -m pytest -q && KLINE_API_BASE_URL=<地址> python -m pytest -m integration -q`
Expected: 全过（个股分时全部既有测试不变）

**Step 4: Commit**

```bash
git add tzt_api/ tests/
git commit -m "feat: 板块分时（G6）——分时实现上移基类 + get_concept_plate_trend 薄封装"
```

**测试标准（Task 5 验收）:**
- 集成：板块当日分时含 `market_date/pre_market/trading`；历史分时（20260821）trading 非空
- 回归：`test_trend_unit.py`、`test_trend_integration.py` 全部原样通过（公开行为零变化）
- 结构守护：`TrendFetcher.fetch_intraday_trend/fetch_history_trend/fetch_trend` 签名未变

---

### Task 6: SecurityResolver —— 10032 意图路由（G1 上）

**Files:**
- Create: `tzt_api/search.py`
- Create: `tests/test_search_unit.py`
- Create: `tests/test_search_integration.py`
- Modify: `tzt_api/__init__.py`、`tests/test_structure_api.py`（导出 + 版本断言留 Task 8）

**Step 1: 单元失败测试 `tests/test_search_unit.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityResolver 单元测试：10032 响应解析与路由决策（mock，无网络）。"""
import pytest

from tzt_api import SecurityResolver


def make_resolver(monkeypatch, payload):
    r = SecurityResolver()
    monkeypatch.setattr(r._client, "request", lambda params, **kw: payload)
    return r


MULTI = {  # 实测样例：000001（2026-08-24）
    "ErrorNo": "2", "MaxCount": "2",
    "BinData": "000001|平安银行|000001|上证指数|",
    "StockLabel": "深A|指数|", "MarketNo": "0|1|",
}
UNIQUE_INDEX = {"ErrorNo": "1", "BinData": "000300|沪深300|", "StockLabel": "指数|", "MarketNo": "1|"}


class TestResolve:
    def test_ambiguous_returns_candidates(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("000001")
        assert result["status"] == "ambiguous"
        assert [c["code"] for c in result["candidates"]] == ["000001", "000001"]
        assert [c["is_index"] for c in result["candidates"]] == [False, True]
        assert result["candidates"][1]["market"] == 1

    def test_unique(self, monkeypatch):
        r = make_resolver(monkeypatch, UNIQUE_INDEX)
        result = r.resolve("000300")
        assert result["status"] == "unique"
        assert result["chosen"]["name"] == "沪深300" and result["chosen"]["is_index"]

    def test_prefer_disambiguates(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("000001", prefer="index")
        assert result["status"] == "unique"
        assert result["chosen"]["name"] == "上证指数"

    def test_not_found(self, monkeypatch):
        from tzt_api import TZTAPIError
        r = SecurityResolver()
        def fail(params, **kw):
            r._client.last_error = TZTAPIError("无结果", error_no="-200608")
            return None
        monkeypatch.setattr(r._client, "request", fail)
        assert r.resolve("不存在的标的")["status"] == "not_found"

    def test_name_exact_match_priority(self, monkeypatch):
        r = make_resolver(monkeypatch, MULTI)
        result = r.resolve("平安银行")   # 假设多候选中含名称精确匹配
        assert result["status"] == "unique" and result["chosen"]["name"] == "平安银行"
```

**Step 2: 实现 `tzt_api/search.py`**

```python
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
        # 复用 KLineFetcher 的配置加载（限流/重试/地址解析一致）
        from tzt_api._base import KLineFetcher  # 局部导入避免模块环
        base = KLineFetcher(config_path=config_path, strict=True)
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
```

`__init__.py` 追加 `from tzt_api.search import SecurityResolver` 与 `__all__` 条目；`test_structure_api.py::test_exports` 集合追加 `"SecurityResolver"`。

**Step 3: 集成测试 `tests/test_search_integration.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SecurityResolver 集成测试（真实网关，2026-08-24 实测样例固化）。"""
import pytest

pytestmark = pytest.mark.integration

from tzt_api import SecurityResolver


@pytest.fixture(scope="module")
def resolver():
    return SecurityResolver()


class TestResolveIntegration:
    def test_unique_index_bare_code(self, resolver):
        r = resolver.resolve("000300")
        assert r["status"] == "unique" and r["chosen"]["is_index"] and r["chosen"]["market"] == 1

    def test_ambiguous_000001(self, resolver):
        r = resolver.resolve("000001")
        assert r["status"] == "ambiguous" and len(r["candidates"]) == 2

    def test_prefer_index(self, resolver):
        r = resolver.resolve("000001", prefer="index")
        assert r["status"] == "unique" and r["chosen"]["name"] == "上证指数"

    def test_chinese_name(self, resolver):
        r = resolver.resolve("贵州茅台")
        assert r["status"] == "unique" and r["chosen"]["code"] == "600519"

    def test_pinyin_fuzzy_multi(self, resolver):
        r = resolver.resolve("zs")
        assert r["status"] == "ambiguous" and len(r["candidates"]) > 1

    def test_not_found(self, resolver):
        r = resolver.resolve("zzzzzz9999")
        assert r["status"] == "not_found"
```

**Step 4: 跑全部**

Run: `python -m pytest -q && KLINE_API_BASE_URL=<地址> python -m pytest tests/test_search_integration.py -m integration -q`
Expected: 全过

**Step 5: Commit**

```bash
git add tzt_api/search.py tzt_api/__init__.py tests/test_search_unit.py tests/test_search_integration.py tests/test_structure_api.py
git commit -m "feat: SecurityResolver——10032 标的意图路由（unique/ambiguous/not_found/error）"
```

**测试标准（Task 6 验收）:**
- 单测 5 项（mock 解析/路由/优先级/未找到/精确名）全过
- 集成 6 项固化实测样例：000300 唯一指数、000001 双候选、prefer=index 命中上证指数、贵州茅台→600519、zs 多候选、乱码 not_found
- 10032 请求经 `accept_error_nos=("1","2")` 通道：日志无重试告警（Task 3 联动）

---

### Task 7: 行情 Skill 交付（SKILL.md + 脚本，G1 下）

**Files:**
- Create: `skill/SKILL.md`
- Create: `skill/scripts/quotes.py`
- Create: `tests/test_skill_script.py`（集成：脚本冒烟）

**Step 1: 实现脚本 `skill/scripts/quotes.py`（核心骨架，完整实现含全部子命令）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行情 Skill 执行入口：agent 经 SKILL.md 调用，输出 JSON。

退出码：0 成功 | 2 未找到标的 | 3 歧义（stdout 打印候选）| 4 网关/配置错误
子命令：
  resolve  <标的词> [--prefer index|stock]        标的解析
  dayk     <代码> [--count N | --begin --end] [--adjust qfq|hfq|none] [--factor]
  mink     <代码> --freq 1min|5min|15min|30min|60min [--count N] [--pages N]
  trend    <代码> [--date YYYYMMDD]               分时（缺省当日）
  plates   <代码> [--type concept|industry|region]
  members  <板块代码> [--all]
  platek   <板块代码> [--freq ...]                 板块日K/分钟K
依赖：tzt-api v2.0.0（pip install -e 本仓库），KLINE_API_BASE_URL 环境变量。
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # 仓库内直跑

from tzt_api import (KLineFetcher, MinKLineFetcher, ConceptPlateFetcher,
                     TrendFetcher, SecurityResolver, MarketResolutionError, TZTError)


def _fetchers():
    return (KLineFetcher(strict=True), MinKLineFetcher(strict=True),
            ConceptPlateFetcher(strict=True), TrendFetcher(strict=True))


def main(argv=None):
    ...  # argparse 分发；每个子命令：
         # 1) 标的词先经 SecurityResolver（resolve 子命令除外：代码可直接跳过）
         # 2) strict fetcher 抛 TZTError/MarketResolutionError → 捕获转
         #    {"error": {"kind": "...", "message": "...", "actionable": "..."}} + 对应退出码
         # 3) 成功 → {"data": [...], "meta": {"count": N, "unit": "元/股/%"}}

if __name__ == "__main__":
    sys.exit(main())
```

（实现要点：`mink`/`dayk` 接受 `sh600519` 显式前缀或裸码；裸 000xxx 捕获 `AmbiguousCodeError` 后自动转 `SecurityResolver` 复析，仍歧义则 exit 3 并打印候选——"歧义即失败"在 skill 层表现为**带着候选清单失败**。）

**Step 2: 编写 `skill/SKILL.md`**

```markdown
---
name: gxquotes
description: >
  A股行情数据技能：日K/分钟K（前/后/不复权+复权因子）、实时与历史分时、个股与
  主要指数、概念板块归属/成份股/板块指数行情（日K+分钟+分时）。触发词：行情、K线、
  分时、复权、指数、概念板块、成份股。数据口径：价格/成交额=元、成交量=股、涨跌幅=%。
---

# 行情 Skill（gxquotes）

## 环境要求
- `KLINE_API_BASE_URL` 环境变量（未设置报错并提示）
- Python ≥3.9 + tzt-api v2.0.0

## 用法（脚本输出 JSON）
（resolve/dayk/mink/trend/plates/members/platek 七个子命令示例，每条给一行真实示例+返回结构）

## 标的解析规则（重要）
- 优先让用户给显式前缀：sh600519 / sz000001 / sh000300（沪深300）/ bj899050
- 裸码 000xxx 或中文名/拼音 → 先 `resolve`；返回 ambiguous 时**向用户列出候选反问**
- 铁律：只读 GET、限流 ≥0.1s、不缓存超过当日、除权说明见需求文档 FR2

## 错误语义（退出码）
- 2 未找到标的（换名称/代码重试）| 3 歧义（打印候选，问用户）| 4 网关/配置（检查环境变量与网络）
```

**Step 3: 脚本冒烟测试 `tests/test_skill_script.py`**

```python
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

    def test_plate_min_kline(self):
        p = run("platek", "994612", "--freq", "5min", "--count", "-3")
        assert p.returncode == 0 and len(json.loads(p.stdout)["data"]) > 0
```

**Step 4: 跑冒烟**

Run: `KLINE_API_BASE_URL=<地址> python -m pytest tests/test_skill_script.py -m integration -q`
Expected: 全过（exit code 语义正确）

**Step 5: Commit**

```bash
git add skill/ tests/test_skill_script.py
git commit -m "feat: 行情 Skill 交付——SKILL.md + quotes.py（JSON 输出/退出码语义/歧义反问）"
```

**测试标准（Task 7 验收）:**
- 5 项冒烟全过：显式前缀日K 3 根、裸 000001 exit 3 + 双候选、乱码 exit 2、当日分时含 trading、板块 5minK
- `python skill/scripts/quotes.py dayk sh600519 --count -3 --adjust none` 手工运行输出合法 JSON
- SKILL.md 含：环境变量说明、七子命令示例、标的解析规则（歧义反问）、错误退出码表、单位口径、安全铁律

---

### Task 8: 发版 2.0.0 + 全量文档同步

**Files:**
- Modify: `pyproject.toml`、`tzt_api/__init__.py`（version 2.0.0）
- Modify: `tests/test_structure_api.py`（版本断言）
- Modify: `CHANGELOG.md`、`README.md`、`AGENTS.md`、`docs/API/接口功能清单.md`、`docs/README.md`

**Step 1: 版本三处** `pyproject.toml` → `version = "2.0.0"`；`__init__.py` → `__version__ = "2.0.0"`；结构测试断言同步。

**Step 2: CHANGELOG 2.0.0 节**（破坏性变更置顶）

```markdown
## [2.0.0] - 2026-08-25

**破坏性变更（FR3 v2 契约，详见 docs/plans/2026-08-24-market-v2-and-routing-design.md）**
- 删除指数白名单与指数优先推断：`INDEX_CODE_MAP`/`is_index`/`get_index_info` 移除；
  取指数一律显式前缀（sh000300 / sz399001 / bj899050）或显式 market
- 裸码 000xxx 抛 `AmbiguousCodeError`、未知段位抛 `UnknownCodeError`（原"默认深"移除）；
  段位规则新增 900（沪B）
- kline-qlib 迁移指引：市场判断改用新 infer_market；取指数改显式前缀

**新增**
- `SecurityResolver`（10032 意图路由：代码/中文名/拼音 → unique/ambiguous/not_found）
- 板块分钟K `get_concept_plate_min_kline` 与板块分时 `get_concept_plate_trend`（G6）
- TZTClient 错误分类：不可重试 ErrorNo fail-fast（-2300/-989903/-200608/-206008）、
  `accept_error_nos` 状态码透传（10032）
- 行情 Skill 交付（skill/SKILL.md + quotes.py，agent skill 形态）
```

**Step 3: 文档同步要点**
- `README.md`：「市场推断与指数优先」整节改写为 v2 契约表 + 显式前缀示例；快速上手补 SecurityResolver 与板块分钟；项目结构补 `search.py`、`skill/`
- `AGENTS.md`：目录约定改 v2（删指数优先行，加 Ambiguous/Unknown 异常与 resolver）；当前状态 v2.0.0
- `docs/API/接口功能清单.md`：market 节改 v2 契约；总览补 SecurityResolver/板块分钟/板块分时；测试数更新
- `docs/README.md` 索引补 skill 说明

**Step 4: 全量验收**

```bash
python -m pytest -q                                   # 单测全过
KLINE_API_BASE_URL=<地址> python -m pytest -m integration -q   # 集成全过
python -c "import tzt_api; assert tzt_api.__version__ == '2.0.0'"
grep -rn "INDEX_CODE_MAP\|is_index\|get_index_info" tzt_api/   # 零命中
```

**Step 5: Commit + Tag**

```bash
git add -A
git commit -m "release: v2.0.0——显式契约 + SecurityResolver + 板块分钟行情 + 行情 Skill"
git tag -a v2.0.0 -m "v2.0.0: explicit market contract, security resolver, plate minute data, quotes skill"
```

**测试标准（Task 8 / 全局验收）:**
- 四条全局验收命令全部通过（见计划头部）
- CHANGELOG 含破坏性变更与迁移指引；README/AGENTS/接口功能清单 无 v1 白名单残留表述（`grep -n "指数优先" README.md AGENTS.md` 仅出现在迁移说明语境）
- `git tag` 列表含 v2.0.0

---

## 执行依赖与顺序

```
Task 1 → Task 2（v2 契约，先破坏先稳定）
Task 3（传输层，独立但 Task 6 依赖其 accept_error_nos）
Task 4 → Task 5（板块分钟，独立于 1-3，可并行）
Task 6（依赖 Task 3）
Task 7（依赖 Task 6 + 1/4/5 的能力）
Task 8（收尾，依赖全部）
```

**kline-qlib 迁移（后续，另仓库）**：其 `converter.code_to_qlib_dir` 裸码 000xxx→sz 行为需与新契约对齐（显式前缀化），在 kline-fetcher 仓库跟进，本计划仅交付迁移指引文档。
