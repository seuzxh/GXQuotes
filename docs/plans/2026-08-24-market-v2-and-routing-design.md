# 设计存档：market.py v2 显式契约 与 10032 意图路由

| | |
|---|---|
| 日期 | 2026-08-24 |
| 状态 | 已评审定稿（brainstorming 流程，逐段确认） |
| 需求 | [行情Skill需求.md](../requirements/行情Skill需求.md) v0.3（FR3/FR6/N6 的完整依据） |

## 0. 决策摘要

| # | 决策 | 依据 |
|---|------|------|
| D1 | **删除指数白名单**（INDEX_CODE_MAP/is_index/get_index_info/指数优先） | 上游明确知晓意图；白名单仅是裸码路由默认值且有覆盖缺口（000009/932000 曾被误判） |
| D2 | 库层**零指数知识**，仅个股段位规则；歧义/未知段位**抛异常**（fail-fast） | 静默猜测 = 静默错数据，是最坏失败模式 |
| D3 | 破坏性变更**彻底移除、直上 v2.0.0**（不留弃用缓冲） | 新哲学下"是否指数"由上游声明，库不需要该判断 |
| D4 | 前缀 = **市场声明**，个股与指数共用 SH/SZ/BJ 命名空间 | qlib 查证（见 §3）+ kline-qlib 目录命名同构 |
| D5 | Skill 层意图路由用 **10032 搜索接口**（SecurityResolver） | 实测可解析裸码歧义 + 中文名/拼音反查，一并解决 Q5 |
| D6 | 无静态别名表（YAGNI） | 别名需求走 10032 名称解析 |

## 1. 库层 market.py v2 契约

### 1.1 推断顺序（infer_market）

```
1. 显式前缀 sh/sz/bj      → 对应市场（个股/指数通用，D4）
2. 调用方显式 market 参数  → 直接使用（Fetcher 层，优先级最高）
3. 裸码段位规则（仅个股，全部 10032 实测标定）：
     600/601/603/605/688/689/900 → 沪(1)     # 900=沪B，实测 900948 伊泰B m=1
     001/002/003/300/301         → 深(0)
     8/4/920                     → 北(103)   # 覆盖 830/430/870/920/899
4. 000xxx → AmbiguousCodeError
5. 其余   → UnknownCodeError    # 含 200(深B，网关无数据 -206008)、93x(中证，零知识)
```

### 1.2 异常体系

- `MarketResolutionError(ValueError)` 基类 + `AmbiguousCodeError` + `UnknownCodeError`，`tzt_api` 顶层导出
- 消息模板（可行动指引）：`"000001 为歧义代码（深市个股/沪市指数共存）：个股请用 sz000001，指数请用 sh000001，或显式传 market"`
- 抛出时机：`_build_params` 阶段（参数构造期），**不发请求即失败**

### 1.3 删除/保留清单（v2.0.0）

| 删除 | 保留 |
|------|------|
| `INDEX_CODE_MAP`（26 指数白名单） | `MARKET_CODE_MAP`（sh/sz/bj→1/0/103） |
| `INDEX_CODE_PREFIXES`（399 规则） | `MARKET_TO_PREFIX`（kline-qlib 目录映射用） |
| `is_index` / `get_index_info` | `numeric_code` |
| `KLineFetcher.is_index/get_index_info` 静态方法 | `infer_market`（重写） |
| 指数优先规则、"默认深"兜底 | |

### 1.4 实测证据（2026-08-24，网关 10032 全段标定）

| 样本 | 结果 | 样本 | 结果 |
|------|------|------|------|
| 600000/601318/603259/605499 | 沪A m=1 | 001979/002594/003816 | 深A m=0 |
| 688981 | 科创板 m=1 | 300750/301269 | 创业板 m=0 |
| 689009 | CDR m=1 | 830799/430047 | 北 m=103（label"已切换"） |
| 920002 | 京A m=103 | 899050 | **指数** m=103（"8"规则恰好覆盖） |
| 900948 | 沪B m=1（**900 段补入依据**） | 200002 | **无结果** -206008（200 段不收依据） |
| 000300 | 唯一候选=指数 m=1 | 000001 | **双候选**（歧义依据） |
| 932000 | 指数 m=1（93x 落未知段→异常，显式 sh932000 取） | | |

### 1.5 连带改造

- `fetch_trade_calendar` 默认 `index_code="000001", market=1` 已显式 → 行为不变
- 26 指数参数化集成测试（test_indices_integration.py）改写为显式前缀/显式 market 形式
- `test_market.py`、`test_structure_api.py` 按新契约重写；README/AGENTS.md 的"指数优先/000001 歧义"章节改写
- kline-qlib 迁移：取指数一律显式前缀；其 converter 的裸码 000xxx→sz 目录行为与本契约的"抛异常"对齐策略在其仓库侧决定

## 2. Skill 层 SecurityResolver（10032 意图路由）

### 2.1 协议

```
输入：标的词（6位代码 / 中文名 / 拼音首字母）
  ↓ Action=10032（代码 → StockCodeList=code；名称/拼音 → StockCode=词, StockCount）
解析：竖线多值字段 BinData|StockLabel|MarketNo|ClientStockType
  → 候选 [{code, name, market, label}]，is_index = (label == "指数")
路由决策：
  唯一候选   → 调行情方法（显式 market）
  多候选     → 名称精确匹配优先；否则列候选反问用户
  -200608/-206008 → 「未找到该标的」
```

### 2.2 实测样例（2026-08-24）

| 输入 | ErrorNo | 结果 |
|------|:---:|------|
| `000300` | 1 | 唯一候选 沪深300(m=1)——裸码歧义被自动消解 |
| `000001` | 2 | 平安银行(深A,m=0) + 上证指数(指数,m=1) → 反问 |
| `贵州茅台` | 1 | 600519(沪A,m=1) |
| `zs` | 2 | 中信证券/招商银行/… 模糊多条 |

### 2.3 前置修正（N2'）

10032 的 `ErrorNo=1/2` 是**结果状态码**（命中一条/多条），非错误——v1.1.0 TZTClient"ErrorNo≠0 即重试"会丢弃有效多候选响应。M2 须为搜索通道增加状态码透传；同批处理不可重试 ErrorNo 分类（-2300 证券代码错误类不应重试 3 次+退避 7s，实测观察）。

## 3. qlib 命名空间查证（D4 依据）

- qlib 官方工作流默认 `benchmark: "SH000300"`，yahoo collector 下载指数即 `SH000300`/`SH000905`（Yahoo 源 `000300.SS`）——**指数行情与个股共用交易所前缀命名空间**（microsoft/qlib issue #1323、官方文档与示例配置）
- `CSI300` 在 qlib 中是 **instruments 池名**（`cn_index/collector.py --index_name CSI300 --method parse_instruments` 生成成分股清单），不是行情代码
- 本地 kline-qlib `converter.code_to_qlib_dir`（2.kline-fetcher/kline_fetcher/converter.py:169）同构：一切证券映射 sh/sz/bj 目录，指数需显式前缀

## 4. 评审记录（brainstorming 流程）

- 2026-08-24 逐段确认：段位规则初稿 → 用户提调整（段位本身 + 歧义处置）→ 10032 全段实测标定 → 修正稿（+900 沪B）确认；000xxx 整段抛异常确认
- 用户质询"指数是否应有特殊前缀"→ qlib 查证 → 定稿：共用命名空间，无别名层
- 设计 2 确认问答中断后由用户定稿："按照指数与个股共用 SH/SZ 命名空间来设计"

## 5. M2 实施顺序（依赖关系）

1. G9 market.py v2 + 异常体系 + 测试改写 → **发版 2.0.0**
2. N2' TZTClient 错误分类 + 10032 状态码透传
3. G1 SecurityResolver（依赖 2）→ SKILL.md 封装 → 验收场景回归
