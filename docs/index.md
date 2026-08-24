# GXQuotes（tzt-api）

中焯行情 3.0 API 的 Python 客户端，专注封装 A 股行情接口：**日K / 分钟K / 概念板块 / 分时**（集合竞价 + 盘中）。
零 numpy 依赖，仅 `requests` + `PyYAML`。

> 仓库名 `GXQuotes`，Python 发行名为 `tzt-api`（`pip install` / `import tzt_api`）——两者指向同一包。
> 本仓库自 [kline-fetcher](https://github.com/seuzxh/kline-fetcher) monorepo 拆分而来；qlib 数据管道在 kline-fetcher 仓库的 `kline-qlib` 包，依赖本包。

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
from tzt_api import KLineFetcher, MinKLineFetcher, ConceptPlateFetcher, TrendFetcher

fetcher = KLineFetcher()                 # 日K + 共享底座
kline = fetcher.fetch_day_kline_with_factor("600519", begindate="20240101", enddate="20241231")

mf = MinKLineFetcher()                   # 分钟K（继承 KLineFetcher）
bars = mf.fetch_min_kline("000001", freq="5min", count=-1500)

pf = ConceptPlateFetcher()               # 概念板块（继承 KLineFetcher）
plates = pf.get_all_concept_plates()

tf = TrendFetcher()                      # 分时（继承 KLineFetcher）
trend = tf.fetch_history_trend("000300", date="20260820")
```

## 市场推断与指数优先（重要）

代码自动推断市场（`sh=1, sz=0, bj=103`），规则收敛在 `tzt_api/market.py` 单一事实源：

- **显式前缀优先**：`sh600519` / `sz000001` / `bj830799` 直接按前缀市场
- **指数优先于个股**：`INDEX_CODE_MAP` 白名单（26 个常见指数）与 `399` 前缀按指数处理
- :warning: **代码歧义**：裸码 `"000001"` 按上证指数（沪市）处理，会遮蔽同代码的深市个股（平安银行）——取深市个股请用 `sz000001` 或显式 `market=0`
- 新增指数：向 `tzt_api/market.py` 的 `INDEX_CODE_MAP` 添加 `{代码: (名称, market)}` 即可

## 测试

```bash
pytest -q                                    # 单元测试（默认跳过 integration 标记）
KLINE_API_BASE_URL=<地址> pytest -m integration   # 集成测试（需真实 API）
```

## 文档导航

- [行情 Skill 需求](requirements/行情Skill需求.md) —— 项目目标、功能/非功能需求、差距分析、里程碑
- [接口功能清单](API/接口功能清单.md) —— 已实现数据接口总览（方法/参数/返回字段/实测状态）
- [中焯官方文档](API/中焯官方文档/README.md) —— 官方资料导航（查什么 → 读哪份）
- [概念板块抓包记录](API/概念板块请求API.md) —— 概念板块接口原始抓包（iOS 客户端）
- [tztapi-agent 使用指南](guide/tztapi-agent.md) —— 接口智能体三类场景与铁律

变更记录见仓库内的 [CHANGELOG.md](https://github.com/seuzxh/GXQuotes/blob/master/CHANGELOG.md)。
