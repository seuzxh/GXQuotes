# Changelog

本文件记录 tzt-api 的版本变更（Keep a Changelog 格式）。

## [Unreleased]

**变更**
- Release Skill 新增包内默认行情配置，Trae Work/Coze 上传后无需依赖会话环境变量；
  `KLINE_API_BASE_URL` 与 `KLINE_CONFIG_PATH` 仍可由管理员显式覆盖
- Skill 指令、CLI 配置/网络错误及传输层日志统一隐藏具体网关地址；网络异常不再透传
  可能包含完整 URL 的 `requests` 原始错误文本
- 打包流程强制校验内部配置存在，并拒绝在用户可见的 `SKILL.md` 或 CLI 中残留具体 IP 地址

## [2.1.0] - 2026-08-27

**新增**
- `MarketRankFetcher.get_market_rank()`：封装 `Action=10006` 市场个股排行；提供
  京沪深A股、沪深A股、沪市、深市、北市、沪深主板、创业板七个内置证券池，
  支持30个普通标量行情字段的服务端排序及升降序，返回固定30字段稳定 schema
- `tzt_api.quote_fields`：把 10005/10006/10007 共用字段 ID、响应键与单位换算收敛为
  单一事实源；10005/10007 原有27字段公共契约保持不变
- 行情 Skill 新增 `market-rank` 子命令：支持 `--scope/--sort/--direction/--limit/--start`，
  严格区分“全市场个股排行”“板块排行”和“板块成份股排行”；新增详细字段 reference
- `ConceptPlateFetcher.get_all_plates()`：统一获取行业/概念/地域/风格板块，
  `plate_type` 分别映射 Action 10007 的 subtype 0/1/2/3，支持 `limit` 和自动翻页；
  新增 27 个普通标量字段的 `sort_by` 与 `direction=asc|desc`；返回行固定携带
  全部 27 个已换算的具名标量 props 字段（缺失为 `None`，906 不解析）；
  `get_all_concept_plates()` 保留为向后兼容入口
- 行情 Skill 新增 `plate-list` 子命令：`--type industry|concept|region|style|all`，
  支持 `--sort` 与 `--direction`；默认每类最多 30 条，显式 `--full` 获取全量；
  `all` 输出每条补充 `type`
- 根目录 `fetch_all_concept_plates.py` 增加 `--type/--sort/--direction`，
  支持按指定字段导出单类或四类全量板块
- `ConceptPlateFetcher.get_concept_plate_stocks()` 与全量迭代器新增 27 个普通
  数值字段的 `sort_by`、`direction=asc|desc`；保持默认涨跌幅降序，返回当前
  排序字段的已换算具名值，并修正 `block.include=1` 下全量分页推进偏移
- 行情 Skill `members` 新增 `--sort/--direction/--limit`，与 `--all` 配合支持
  板块成份股排行；输出 `meta.sort/retrieved_at` 供 Agent 明确数据口径

**优化**
- Action 10005 成份股排行默认 `props` 移除未解析的完整盘中分时数组
  `43 TrendOp`，显著降低响应体积、JSON解码与分页开销；公开方法签名、27个
  排序字段、返回 schema 及 Skill `members` 行为保持不变

**验证**
- 单元测试368项、真实网关集成测试200项全部通过；10006七个内置证券池及30个
  排序字段均完成实测，Skill Release 包在隔离虚拟环境中通过启动冒烟

## [2.0.0] - 2026-08-25

M2 里程碑发版：market v2 显式契约 + SecurityResolver 标的意图路由 + 板块分钟行情 + 行情 Skill 交付。测试规模：单元 134 项 + 集成 109 项全部通过（2026-08-25 实测网关）。

**破坏性变更（FR3 v2 契约，详见 [docs/plans/2026-08-24-market-v2-and-routing-design.md](docs/plans/2026-08-24-market-v2-and-routing-design.md)）**
- 删除指数白名单与指数优先推断：`INDEX_CODE_MAP`/`INDEX_CODE_PREFIXES`/`is_index`/`get_index_info` 移除；
  取指数一律显式前缀（sh000300 沪深300 / sz399001 深证成指 / bj899050 北证50）或显式 market
- 裸码 000xxx 抛 `AmbiguousCodeError`、未知段位抛 `UnknownCodeError`（原"默认深"与 v1 "000001→上证指数"遮蔽规则移除）；
  段位规则新增 900（沪B）与 920（北交所现行码段，2026 由 83/43/87 切换而来，旧码 fail-fast 并提示 920 切换）
- kline-qlib 迁移指引：市场判断改用新 `infer_market`；取指数改显式前缀；
  其 `converter.code_to_qlib_dir` 裸码 000xxx→sz 行为需与新契约对齐（在 kline-fetcher 仓库跟进）

**新增**
- `SecurityResolver`（`tzt_api/search.py`，10032 意图路由：6 位代码/中文名/拼音首字母 → unique/ambiguous/not_found/error，
  支持 `prefer="index"/"stock"` 意图过滤）
- 板块分钟K `get_concept_plate_min_kline` 与板块分时 `get_concept_plate_trend`（G6，market=44 通道；
  分钟K/分时私有实现上移基类 `_fetch_kline_series`/`_fetch_trend_raw`，与个股侧 DRY 复用）
- TZTClient 错误分类：不可重试 ErrorNo fail-fast（-2300/-989903/-200608/-206008，不再 3 次重试 + 退避）、
  `accept_error_nos` 结果状态码透传（10032 的 ErrorNo=1/2 按成功返回）
- 行情 Skill 交付（`skill/SKILL.md` + `skill/scripts/quotes.py`，agent skill 形态）：
  八子命令（resolve/dayk/mink/trend/plates/members/platek/platetrend），stdout 输出 JSON，
  退出码 0 成功 / 2 未找到 / 3 歧义（打印候选供反问）/ 4 网关配置错误；裸码歧义自动经 SecurityResolver 复析

## [1.1.0] - 2026-08-24

架构优化（服务行情 Skill 目标，M1）+ 板块接口能力修正。公共 API 向后兼容（kline-qlib 无感）。

**新增**
- `tzt_api/_transport.py`：`TZTClient` 共享传输层——会话复用、重试（指数退避）、**进程级共享限流**（此前限流按 Fetcher 实例隔离，多实例混用时对网关实际速率是配置的 N 倍；2026-08-24 实测修正）
- 类型化异常 `TZTError` / `TZTConnectionError`（网络层）/ `TZTAPIError`（ErrorNo≠0，携带 ErrorNo）；Fetcher 新增 `strict` 初始化参数（默认 False，行为不变；True 时失败抛类型化异常）与 `last_error` 属性——为 Skill 层错误自诊断铺路
- `ConceptPlateFetcher.iter_concept_plate_stocks()`：自动翻页产出板块全部成份股的生成器（剔除板块自身行）

**变更（含行为变化）**
- `get_all_concept_plates()` 自动翻页返回**全量**概念板块（实测约 390 个、4 页；此前仅返回按涨跌幅排序前 30 条）；新增 `limit` 参数可截断
- 板块列表/成份股快照字段统一换算：`price`/`change`/`high`/`low` ÷1e6 → 元/点，`change_pct` ÷1000 → %（2026-08-24 实测标定自洽；此前返回原始整数）
- 市场前缀剥离统一走 `market.numeric_code`（移除 `_base`/`trend` 中各自的 `lstrip` hack）

**内部**
- `fetch_intraday_trend`/`fetch_history_trend` 合并实现为 `_fetch_trend`（~90% 重复消除）；K线响应提取统一 `_extract_kline_list`（4 文件 5 处样板收敛）
- 测试：新增 `tests/conftest.py`（集成跳过条件单点化 + session 级共享 fixtures）；重写 `test_concept_plates.py`（unittest→pytest，删 sys.path hack 与 kline-fetcher 残留注释，新增全量分页/单位自洽/生成器深度用例）；新增 `test_transport.py`（16 项：共享限流/重试/异常/base_url 优先级）；与 `test_split_interfaces.py` 重叠用例去重
- 文档：目录重组为 `docs/requirements`（需求）/ `docs/API`（接口文档）/ `docs/guide`（指南）三级 + `docs/README.md` 索引；新增 [docs/requirements/行情Skill需求.md](docs/requirements/行情Skill需求.md)（项目目标、FR/NFR、差距分析对齐 v1.1.0、M1 完成 / M2 待启动）
- 需求评审（2026-08-24 第二轮）：需求文档升至 v0.3——**FR3 标的解析契约 v2 定稿**（删除指数白名单、库层零指数知识、个股与指数共用交易所前缀命名空间、段位规则 10032 全段实测标定、000xxx/未知段位抛 `AmbiguousCodeError`/`UnknownCodeError`）、**FR6 定稿 10032 意图路由**（SecurityResolver，兼解决中文名/拼音反查）、N6 改写为 v2.0.0 破坏性变更；设计存档见 `docs/plans/2026-08-24-market-v2-and-routing-design.md`（M2 实施依据）
- 需求落定（2026-08-24 第三轮，v0.4）：待确认问题全部关闭——Q1 定为 **agent skill 形态**（排除 MCP/CLI）、Q3 **板块分钟行情纳入 FR5**（网关实测支持：板块 1/5/15min K 与分时 TrendOp 241 点，market=44 通道复用，M2 薄封装）、Q4 分时**按需拉取**（不做轮询/订阅）

## [1.0.0] - 2026-08-23

- 自 kline-fetcher v3.0.1 拆分建包：KLineFetcher/_base、MinKLineFetcher、ConceptPlateFetcher、TrendFetcher 及 config
- 新增 `tzt_api.market` 市场规则单一事实源（原 `_base` 常量与 infer_market/is_index/get_index_info 纯函数化；`KLineFetcher` 对应静态方法改为委托）
- 依赖仅 requests + PyYAML（不再连带 numpy）
- 2026-08-24：自 kline-fetcher monorepo（9b9613c）整体迁出，独立建仓 **GXQuotes**（github.com/seuzxh/GXQuotes）；中焯官方文档归档、概念板块接口资料与 tztapi-agent 指南随迁至本仓 `docs/`
- 2026-08-24：新增 `docs/接口功能清单.md` —— 已实现数据接口总览（12 个公开方法，含实测状态；当日 180 项测试全部通过）
