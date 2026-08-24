# GXQuotes（tzt-api）

中焯行情 3.0 API 的 Python 客户端，专注封装 A 股行情接口：日K / 分钟K / 概念板块 / 分时（集合竞价 + 盘中）。零 numpy 依赖，仅 requests + PyYAML。

> 仓库名 `GXQuotes`，Python 发行名为 `tzt-api`（`pip install` / `import tzt_api`）——两者指向同一包。
> 本仓库自 [kline-fetcher](https://github.com/seuzxh/kline-fetcher) monorepo 拆分而来（extracted from kline-fetcher@9b9613c）；qlib 数据管道（下载编排 + bin 格式转换）在 kline-fetcher 仓库的 `kline-qlib` 包，依赖本包。

## 安装

```bash
# 从源安装
pip install git+https://github.com/seuzxh/GXQuotes.git

# 本地开发
git clone https://github.com/seuzxh/GXQuotes.git
pip install -e ./GXQuotes
```

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `KLINE_API_BASE_URL` | **中焯行情 API 地址（必填）** | 无，未配置时报 `EnvironmentError` |
| `KLINE_CONFIG_PATH` | 自定义配置文件路径 | 包内 `config/kline_config.yaml` |

## 快速上手

```python
from tzt_api import (KLineFetcher, MinKLineFetcher, ConceptPlateFetcher,
                     TrendFetcher, SecurityResolver)

fetcher = KLineFetcher()                 # 日K + 共享底座
kline = fetcher.fetch_day_kline_with_factor("600519", begindate="20240101", enddate="20241231")

mf = MinKLineFetcher()                   # 分钟K（继承 KLineFetcher）
bars = mf.fetch_min_kline("sz000001", freq="5min", count=-1500)   # 深市裸 000xxx 需前缀（见下节）

pf = ConceptPlateFetcher()               # 概念板块（继承 KLineFetcher）
plates = pf.get_all_concept_plates()
min_bars = pf.get_concept_plate_min_kline("994612", freq="5min", count=-240)  # 板块分钟K（v2.0.0）
plate_trend = pf.get_concept_plate_trend("994612")                           # 板块分时（v2.0.0）

tf = TrendFetcher()                      # 分时（继承 KLineFetcher）
trend = tf.fetch_history_trend("sh000300", date="20260820")       # 指数一律显式前缀

resolver = SecurityResolver()            # 标的意图路由（10032，v2.0.0）
resolver.resolve("平安银行")             # → {"status": "unique", "chosen": {code, name, market, is_index}}
resolver.resolve("000001")               # → {"status": "ambiguous", "candidates": [平安银行(sz), 上证指数(sh)]}
resolver.resolve("000001", prefer="index")  # 意图过滤 → 唯一命中上证指数
```

Agent/Skill 场景可直接用脚本（stdout 输出 JSON，退出码 0/2/3/4 表语义）：

```bash
python skill/scripts/quotes.py resolve 贵州茅台          # 标的解析（代码/中文名/拼音）
python skill/scripts/quotes.py dayk sh600519 --count -3  # 日K（歧义裸码自动复析，多候选 exit 3 反问）
python skill/scripts/quotes.py platek 994612 --freq 5min # 板块分钟K（platetrend 为板块分时）
```

## 标的解析（v2 显式契约，重要）

代码自动推断市场（`sh=1, sz=0, bj=103`），规则收敛在 `tzt_api/market.py` 单一事实源。v2.0.0 起判断顺序为 **显式前缀 > 个股段位 > 抛异常**（零指数知识，2026-08 经 10032 全段实测标定）：

**个股段位规则（裸码直判）**

| 市场 | 段位 | 说明 |
|------|------|------|
| 沪 `sh`=1 | `600 / 601 / 603 / 605 / 688 / 689 / 900` | 900=沪B |
| 深 `sz`=0 | `001 / 002 / 003 / 300 / 301` | |
| 北 `bj`=103 | `920` | 北交所现行码段（2026 由 83/43/87 切换而来；921-929 未分配） |

**显式前缀（个股与指数共用 sh/sz/bj 命名空间，指数取数推荐方式）**

- `sh600519` 贵州茅台 · `sh000300` 沪深300 · `sh000905` 中证500 · `sh932000` 中证2000
- `sz000001` 平安银行（深市个股）· `sz399001` 深证成指 · `sz399006` 创业板指
- `bj920001` 北交所个股 · `bj899050` 北证50

**歧义与未知段位抛异常（fail-fast，替代 v1 "默认深/指数优先"）**

- 裸码 `000xxx` 抛 `AmbiguousCodeError`：深市个股与沪市指数真实共存（实测 `000001` = 平安银行 + 上证指数），静态不可分——个股用 `sz000xxx`、指数用 `sh000xxx`，或显式传 `market`
- 其余未知段位（含 `399xxx`/`93xxxx` 等指数裸码、北交所旧码 `83/43/87`、深B `200xxx`）抛 `UnknownCodeError`：请用显式前缀或显式传 `market`；北交所旧码错误消息含 920 切换指引
- 中文名/拼音首字母反查与歧义候选枚举 → `SecurityResolver`（`tzt_api/search.py`，上游 10032）

## 项目结构

```
GXQuotes/
├── tzt_api/
│   ├── market.py         # 市场规则单一事实源（v2 显式契约：段位规则/infer_market/解析异常）
│   ├── _transport.py     # TZTClient 传输层：会话/进程级共享限流/重试/错误分类（v1.1.0+）
│   ├── _base.py          # KLineFetcher 基类：组合 TZTClient + 单位换算 + 日K + 分钟K/分时共享实现
│   ├── min_kline.py      # MinKLineFetcher：分钟K
│   ├── concept_plate.py  # ConceptPlateFetcher：概念板块（列表/日K/分钟K/分时/成份股/归属）
│   ├── trend.py          # TrendFetcher：分时
│   ├── search.py         # SecurityResolver：10032 标的意图路由（v2.0.0）
│   └── config/kline_config.yaml
├── skill/                # 行情 Skill 交付：SKILL.md + scripts/quotes.py 八子命令（v2.0.0）
├── tests/                # 单元 + 集成测试（conftest.py 共享 fixtures）
└── docs/
    ├── README.md         # 文档索引
    ├── requirements/     # 需求（行情Skill需求.md）
    ├── plans/            # 设计存档（market v2 与路由设计等）
    ├── API/              # 接口文档（接口功能清单 / 中焯官方文档 / 概念板块）
    └── guide/            # 使用指南（tztapi-agent）
```

## 测试

```bash
pytest -q                      # 单元测试（默认跳过 integration 标记）
KLINE_API_BASE_URL=<地址> pytest -m integration   # 集成测试（需真实 API）
```

## 文档

目录索引见 [docs/README.md](docs/README.md)（requirements 需求 / API 接口文档 / guide 指南）：

- [docs/requirements/行情Skill需求.md](docs/requirements/行情Skill需求.md) —— 行情 Skill 项目目标与需求基线
- [docs/API/接口功能清单.md](docs/API/接口功能清单.md) —— 已实现数据接口总览（方法/参数/返回字段/实测状态）
- [docs/API/中焯官方文档/README.md](docs/API/中焯官方文档/README.md) —— 官方资料导航（查什么 → 读哪份）
- [docs/API/concept_plate_api.md](docs/API/concept_plate_api.md) —— 概念板块接口文档
- [docs/guide/tztapi-agent.md](docs/guide/tztapi-agent.md) —— 接口智能体使用指南

## 变更记录

见 [CHANGELOG.md](CHANGELOG.md)。
