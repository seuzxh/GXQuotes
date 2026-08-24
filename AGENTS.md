# GXQuotes（tzt-api 包）项目说明

## 项目定位

中焯行情 3.0 API 的 Python 客户端（发行名 `tzt-api`，`import tzt_api`），只做行情接口封装：日K / 分钟K / 概念板块 / 分时。零 numpy；依赖 requests + PyYAML。qlib 数据管道在 [kline-fetcher](https://github.com/seuzxh/kline-fetcher) 仓库（依赖本包）。

## 怎么跑

- 环境：`~/miniconda3/envs/qlib/`（系统 python 无 pytest）；命令用 `conda run -n qlib <cmd>`
- 必填环境变量 `KLINE_API_BASE_URL`（中焯行情 API 地址，未配置报 EnvironmentError）；`KLINE_CONFIG_PATH` 可选
- 测试：`pytest -q`（默认跳过 integration）；`KLINE_API_BASE_URL=<地址> pytest -m integration`

## 目录与约定

- `tzt_api/market.py` 是**市场规则单一事实源**（v2 显式契约：个股段位规则 / `infer_market` / `AmbiguousCodeError`/`UnknownCodeError` 解析异常），勿在其他模块复制规则
- 市场推断 v2 契约：**显式前缀 > 个股段位 > 抛异常**——裸码 000xxx 抛 `AmbiguousCodeError`（深市个股/沪市指数实测共存，静态不可分），未知段位抛 `UnknownCodeError`（fail-fast，v1 "默认深"已删）；指数一律显式前缀（`sh000300`/`sz399001`/`bj899050`）；北交所现行码段 **920**（旧码 83/43/87 已切换，fail-fast 且错误消息带 920 切换指引）
- 标的意图路由：`tzt_api/search.py` 的 `SecurityResolver`（上游 10032；6 位代码/中文名/拼音 → unique/ambiguous/not_found/error，**永不抛出**）；多候选由上层（Skill 层）向用户反问
- 类继承：`KLineFetcher`(_base) ← MinKLineFetcher / ConceptPlateFetcher / TrendFetcher；分钟K/分时私有实现已上移基类（`_fetch_kline_series` / `_fetch_trend_raw`，v2.0.0）供个股与板块复用，勿在子类各写一份
- 传输层（v1.1.0+）：`_transport.py` 的 `TZTClient` 持有会话/重试/**进程级共享限流**（≥0.1s）/**错误分类**——不可重试 ErrorNo（-2300/-989903/-200608/-206008）fail-fast 不再退避重试，`accept_error_nos` 透传 10032 的结果状态码（ErrorNo=1/2）；Fetcher 组合 `_client`，`_request`/`_throttle` 为兼容委托——新代码勿在 Fetcher 内直接发 HTTP
- Skill 交付（v2.0.0）：`skill/SKILL.md` + `skill/scripts/quotes.py` 八子命令（resolve/dayk/mink/trend/plates/members/platek/platetrend），stdout 输出 JSON、退出码 0 成功/2 未找到/3 歧义（打印候选）/4 网关配置错——改子命令行为须同步 SKILL.md 契约
- 失败语义：默认失败返回 None（兼容）；`strict=True` 时抛 `TZTError` 子类（`TZTConnectionError` 网络层 / `TZTAPIError` 网关业务错），`fetcher.last_error` 可查最近失败原因
- 单位换算：价格万分之一元→元（÷1e6）、成交额万元→元（÷1e4）、成交量股、比率类（涨跌幅/换手率）千分之一→%（÷1000）；板块快照字段 v1.1.0 起已统一换算

## 中焯官方接口文档（智能体必读）

接口信息（Action 功能号、入出参、属性 ID、字段单位、市场代码）优先读 [docs/API/中焯官方文档/README.md](docs/API/中焯官方文档/README.md)（6 份解析版 + originals/，含「查什么→读哪份」导航）；接口总览见 [docs/API/接口功能清单.md](docs/API/接口功能清单.md)，概念板块详见 [docs/API/concept_plate_api.md](docs/API/concept_plate_api.md)，项目需求见 [docs/requirements/行情Skill需求.md](docs/requirements/行情Skill需求.md)。

**派发规则**：中焯接口需求（新建/校验/解析问题）必须调用子智能体 `tztapi-agent`（ZCode：Skill `tztapi-agent`；Claude Code：subagent）。其准则：结论以官方文档为据、以真实 API 实测定论。

## 当前状态

- v2.0.0（2026-08-25，M2 完成）：market v2 显式契约（破坏性）+ TZTClient 错误分类 + 板块分钟K/分时 + SecurityResolver 意图路由 + 行情 Skill（skill/）。测试基线：单测 134 + 集成 109 全过。v1.1.0（2026-08-24）；v1.0.0 于 2026-08-23 建、2026-08-24 独立建仓
- 待办：kline-qlib 迁移跟进（`converter.code_to_qlib_dir` 裸码 000xxx→sz 行为与新契约对齐、取指数改显式前缀——在 kline-fetcher 仓库侧进行，本仓已交付迁移指引见 CHANGELOG 2.0.0 节）
