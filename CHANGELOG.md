# Changelog

本文件记录 tzt-api 的版本变更（Keep a Changelog 格式）。

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

## [1.0.0] - 2026-08-23

- 自 kline-fetcher v3.0.1 拆分建包：KLineFetcher/_base、MinKLineFetcher、ConceptPlateFetcher、TrendFetcher 及 config
- 新增 `tzt_api.market` 市场规则单一事实源（原 `_base` 常量与 infer_market/is_index/get_index_info 纯函数化；`KLineFetcher` 对应静态方法改为委托）
- 依赖仅 requests + PyYAML（不再连带 numpy）
- 2026-08-24：自 kline-fetcher monorepo（9b9613c）整体迁出，独立建仓 **GXQuotes**（github.com/seuzxh/GXQuotes）；中焯官方文档归档、概念板块接口资料与 tztapi-agent 指南随迁至本仓 `docs/`
- 2026-08-24：新增 `docs/接口功能清单.md` —— 已实现数据接口总览（12 个公开方法，含实测状态；当日 180 项测试全部通过）
