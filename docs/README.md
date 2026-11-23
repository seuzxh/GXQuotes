# GXQuotes 文档索引

> 目录结构（2026-08-24 重组）：`requirements/` 需求 · `plans/` 设计存档 · `API/` 接口文档 · `guide/` 使用指南

## requirements/ — 需求

- [行情Skill需求.md](requirements/行情Skill需求.md) —— 行情 Skill 项目目标、功能/非功能需求（v0.3：FR3 标的解析 v2 契约、FR6 10032 意图路由已定稿）、差距分析、里程碑

## plans/ — 设计存档

- [2026-08-24-market-v2-and-routing-design.md](plans/2026-08-24-market-v2-and-routing-design.md) —— market.py v2 显式契约（删白名单/段位规则/异常体系）与 SecurityResolver 10032 路由的完整设计记录与实测证据
- [2026-08-25-m2-implementation.md](plans/2026-08-25-m2-implementation.md) —— M2 实施计划（market v2 / 错误分类 / 板块分钟行情 / SecurityResolver / 行情 Skill，Task 1-8）

## API/ — 接口文档

- [接口功能清单.md](API/接口功能清单.md) —— 已实现数据接口总览（18 个公开方法 + 传输层，方法/参数/返回字段/实测状态）
- [中焯官方文档/README.md](API/中焯官方文档/README.md) —— 官方资料导航（6 份解析版 + originals 原件，「查什么 → 读哪份」）
- [concept_plate_api.md](API/concept_plate_api.md) —— 概念板块接口文档（参数/字段/单位/分页语义）
- [market_rank_api.md](API/market_rank_api.md) —— Action 10006 市场个股排行（证券池/排序/字段/单位）
- [概念板块请求API.md](API/概念板块请求API.md) —— 概念板块接口原始抓包记录（iOS 客户端）

## guide/ — 使用指南

- [tztapi-agent.md](guide/tztapi-agent.md) —— 中焯行情接口开发指南（仓库内即可查文档、封装和测试；说明如何选用独立 tztapi-agent）

## skill/ — 行情 Skill 交付（仓库根，v2.1.0）

- [../skill/SKILL.md](../skill/SKILL.md) —— agent skill 入口：十个子命令（含四类板块 `plate-list` 与个股 `market-rank`）、JSON 输出契约、退出码语义（0/2/3/4）、标的解析规则与安全铁律
