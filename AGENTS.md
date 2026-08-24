# GXQuotes（tzt-api 包）项目说明

## 项目定位

中焯行情 3.0 API 的 Python 客户端（发行名 `tzt-api`，`import tzt_api`），只做行情接口封装：日K / 分钟K / 概念板块 / 分时。零 numpy；依赖 requests + PyYAML。qlib 数据管道在 [kline-fetcher](https://github.com/seuzxh/kline-fetcher) 仓库（依赖本包）。

## 怎么跑

- 环境：`~/miniconda3/envs/qlib/`（系统 python 无 pytest）；命令用 `conda run -n qlib <cmd>`
- 必填环境变量 `KLINE_API_BASE_URL`（中焯行情 API 地址，未配置报 EnvironmentError）；`KLINE_CONFIG_PATH` 可选
- 测试：`pytest -q`（默认跳过 integration）；`KLINE_API_BASE_URL=<地址> pytest -m integration`

## 目录与约定

- `tzt_api/market.py` 是**市场规则单一事实源**（INDEX_CODE_MAP / infer_market / is_index 等），勿在其他模块复制规则
- **指数优先**市场推断；⚠️ 裸码 000xxx 指数遮蔽同代码深市个股（"000001"→上证指数，深市个股用 `sz000001` 或 `market=0`）
- 新增指数 → 改 `market.py` 的 `INDEX_CODE_MAP`
- 类继承：`KLineFetcher`(_base) ← MinKLineFetcher / ConceptPlateFetcher / TrendFetcher
- 单位换算：价格万分之一元→元（÷1e6）、成交额万元→元（÷1e4）、成交量股

## 中焯官方接口文档（智能体必读）

接口信息（Action 功能号、入出参、属性 ID、字段单位、市场代码）优先读 [docs/API/中焯官方文档/README.md](docs/API/中焯官方文档/README.md)（6 份解析版 + originals/，含「查什么→读哪份」导航）。概念板块接口详见 [docs/concept_plate_api.md](docs/concept_plate_api.md)。

**派发规则**：中焯接口需求（新建/校验/解析问题）必须调用子智能体 `tztapi-agent`（ZCode：Skill `tztapi-agent`；Claude Code：subagent）。其准则：结论以官方文档为据、以真实 API 实测定论。

## 当前状态

- v1.0.0（2026-08-23 建，2026-08-24 自 kline-fetcher@9b9613c 独立建仓）
- 待办：无既定任务；兄弟项目仍在通过 kline-fetcher 兼容壳间接使用本包，迁移由 kline-fetcher 侧跟进
