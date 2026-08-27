---
name: gxquotes
description: >
  A股行情数据技能：日K/分钟K（前/后/不复权 + 复权因子）、实时与历史分时、个股与
  主要指数、行业/概念/地域/风格板块列表、个股板块归属/成份股/板块指数
  行情（日K + 分钟K + 分时），以及京沪深A股/沪市/深市/北交所个股排行。
  触发词：行情、K线、分时、复权、指数、涨幅榜、个股排行、行业板块、概念板块、
  地域板块、风格板块、成份股、板块。数据口径：价格/成交额=元、成交量=股、
  涨跌幅=%。
---

# 行情 Skill（gxquotes）

统一入口 `skill/scripts/quotes.py`：**stdout 输出 JSON**（`ensure_ascii=False, indent=2`），
日志走 stderr；退出码表达语义（见下方退出码表）。所有请求均为只读 GET。

## 环境要求

- 环境变量 `KLINE_API_BASE_URL`（必配，行情网关地址）。未配置时脚本 exit 4，
  `error.message` 附配置指引。配置方式：
  `export KLINE_API_BASE_URL="http://183.242.5.14:7778"`
  （或写入 `tzt_api/config/kline_config.yaml` 的 `api.base_url`）
- Coze / GitHub Release 产物以 Python 3.11 为运行时目标，并在 `scripts/vendor/`
  内携带 tzt-api v2.1.0、requests、PyYAML 等全部 Python 依赖，可直接执行；
  tzt-api 库本身支持 Python ≥3.9。在 GXQuotes 仓库内开发时，脚本会优先加载仓库源码。

## 单位口径（全部子命令统一）

- 价格（open/high/low/close/price）：**元**（板块指数为点，均已由库换算）
- 成交额（amount/turnover）：**元**
- 成交量（volume）：**股**（非手）
- 涨跌幅（change_pct）：**%**

## 十个子命令（示例均可直接运行）

### 1. resolve — 标的解析

```bash
python skill/scripts/quotes.py resolve 平安银行
```

exit 0 → `{"data": {"term","status":"unique","chosen":{"code","name","market","label","is_index"},"candidates":[...]}, "meta": {"count": N}}`

- `resolve 000001` → exit 3（双候选：平安银行 sz / 上证指数 sh）
- `resolve zzzzzz9999` → exit 2
- `--prefer index|stock`：多候选时按意图过滤（如 `resolve 000001 --prefer index` 唯一命中上证指数）

### 2. dayk — 日K线

```bash
python skill/scripts/quotes.py dayk sh600519 --count -3 --adjust none
```

exit 0 → `{"data": [{"date","open","high","low","close","volume","amount"}], "meta": {"count": 3}}`

- `--count N`：负数=最近 N 根（缺省 -120，按需拉取）
- `--begin/--end YYYYMMDD`：区间取数（优先于 --count）
- `--adjust qfq|hfq|none`：前复权/后复权/不复权（缺省沿用网关默认 cqtype）
- `--factor`：附带复权因子（每根附 `factor` 字段，忽略 --adjust）

### 3. mink — 分钟K线

```bash
python skill/scripts/quotes.py mink sz399001 --freq 5min --count -3
```

exit 0 → `{"data": [{"date","time","open","high","low","close","volume","amount"}], ...}`（带 `time` 字段）

- `--freq` 必填：1min/5min/15min/30min/60min；`--count` 缺省 -240；`--pages N` locator 翻页（默认 1）

### 4. trend — 个股分时

```bash
python skill/scripts/quotes.py trend sh600519
```

exit 0 → `{"data": {"market_date","pre_market":[...],"trading":[{"date","time","last_price","avg_price","volume","turnover"}]}, "meta": {"count": N, "pre_market_count": M}}`

- `--date YYYYMMDD`：历史分时（缺省当日）

### 5. plate-list — 板块列表/排行

```bash
python skill/scripts/quotes.py plate-list --type concept --sort change_pct --direction desc --limit 30
```

exit 0 → `{"data": [{"code","name","market", "<27个普通标量props字段>"}], "meta": {"count", "market":44, "type", "subtype", "full", "sort", "retrieved_at"}}`

- `--type industry|concept|region|style|all`：默认 `concept`；`all` 按
  industry → concept → region → style 的固定顺序合并，每条数据补 `type`。
- 默认 `--limit 30`；`all` 时表示每类最多 30 个。用户明确说“全部/全量”时才用
  `--full`，库层自动翻页。`--limit` 与 `--full` 互斥。
- `--sort` 默认 `change_pct`，`--direction asc|desc` 默认 `desc`。每条数据固定
  返回请求 props 中除 906 外的 27 个普通标量具名字段；缺失值为 `null`，不使用
  通用 `sort_value`。完整字段、单位和自然语言映射见
  [板块排序字段](references/plate-sort-fields.md)。
- `meta.sort` 和 `meta.retrieved_at` 记录排序口径。`full=true`
  仅表示客户端未主动截断；多页动态排行不是强一致快照，市场波动时可能出现页间漂移。
- 自然语言路由：“行业板块/概念板块/地域板块/风格板块”直接映射到对应
  `--type`；“所有类型板块”映射到 `--type all`。

### 6. plates — 个股所属板块

```bash
python skill/scripts/quotes.py plates sh600519 --type concept
```

exit 0 → `{"data": [{"code","name","market","type":"concept|industry|region"}], ...}`

- `--type concept|industry|region`：过滤；缺省返回全部并带 `type` 字段

### 7. members — 板块成份股

```bash
python skill/scripts/quotes.py members 994612 --sort change_pct --direction desc --limit 30
```

exit 0 → `{"data": [{"code","name","market","price","change","change_pct","high","low","<选中的排序字段>"}], "meta": {"count","plate","full","sort","retrieved_at"}}`

- `--sort` 与 `--direction asc|desc` 的字段和自然语言映射与 `plate-list`
  共用[板块与成份股排序字段](references/plate-sort-fields.md)；默认涨跌幅降序。
- 默认 `--limit 50`，可指定前 N 只；超过100时自动按网关单页上限分页并有界
  截取。`--all` 自动翻页拉取全量，与 `--limit` 互斥。
- 输出已剔除 `market=44` 的板块自身占位行；保持基础快照字段，并追加当前
  排序字段的具名值，不使用 `sort_value`。价格类在此表示股票价格（元）。
- `meta.sort` 与 `meta.retrieved_at` 记录排行口径；全量实时排行分页不是强一致快照，
  市场波动时可能出现页间漂移。

### 8. platek — 板块指数K线

```bash
python skill/scripts/quotes.py platek 994612 --freq 5min --count -3
```

exit 0 → 分钟K（结构同 mink，带 `time` 字段）。不给 `--freq` 则为日K（结构同 dayk，缺省 -120 根）。

### 9. platetrend — 板块指数分时

```bash
python skill/scripts/quotes.py platetrend 994612
```

exit 0 → 结构同 trend（`market_date/pre_market/trading`）；`--date YYYYMMDD` 取历史。

### 10. market-rank — 市场个股排行

```bash
python skill/scripts/quotes.py market-rank --scope all-a --sort change_pct --direction desc --limit 50
```

exit 0 → `{"data": [{"code","symbol","name","market","market_name","<30个普通标量行情字段>"}], "meta": {"count","max","scope","markettype","routemarkets","start","limit","sort","retrieved_at"}}`

- `--scope all-a|hs-a|sh-a|sz-a|bj-a|main|gem`：默认 `all-a`（京沪深A股）；
  分别表示沪深A股、上证A股、深证A股、北证A股、沪深主板、创业板。
- `--sort` 默认 `change_pct`，`--direction asc|desc` 默认 `desc`；字段含义、单位、
  scope 映射见[市场个股排行字段](references/market-rank-fields.md)。
- `--limit` 只能为 1–100，默认30；`--start` 默认0。10006是实时排行窗口，跨页
  不是强一致快照，因此本命令不提供 `--all`。
- 返回证券池默认包含新股、ST等符合市场类型的证券；不得把结果描述为“排除ST/新股”榜单。
- 自然语言路由：
  - “当前/A股/全市场/沪市/深市/北交所 + 个股/股票 + 排行” → `market-rank`；
  - “涨幅前N只个股/跌幅前N只股票/涨幅最高N只/排名前N” → `market-rank`，
    即使用户没有说“排行”或“榜”也应命中；
  - “行业/概念/地域/风格板块排行” → `plate-list`（对象是板块）；
  - “某板块内/成份股排行” → `members`（对象是板块内股票）。
  对象仍不明确时先反问，不要用板块排行冒充个股排行。

## 标的解析规则（重要）

1. **显式前缀优先**：优先让用户给出 `sh600519` / `sz000001` / `sh000300`（沪深300）/
   `bj899050`（北证50）。前缀即市场声明（个股与指数共用 sh/sz/bj 命名空间），直接取数不再解析。
2. **裸码**：合法个股段位（600/601/603/605/688/689/900→沪；001/002/003/300/301→深；
   920→北）直接取数；其余裸码（含 000xxx、399xxx、93xxxx、北交所旧码 83/43/87）在发请求前
   抛 Ambiguous/Unknown 异常，脚本**自动调 SecurityResolver 复析**：
   - unique → 用 chosen 的 code+market 自动重试并返回数据（如 `dayk 贵州茅台` 直接成功）
   - ambiguous → exit 3 打印候选，**必须向用户列出候选反问**。
     例：`dayk 000001 --count -1` → exit 3，candidates 恰 2 条
     （000001 平安银行 sz / 000001 上证指数 sh），请用户指定后带前缀重试
   - not_found → exit 2
3. **中文名/拼音**：dayk/mink/trend/plates 的 `<代码>` 参数同样支持（走上述复析通道），
   或先 `resolve` 再取数。
4. **板块列表与代码直传**：用户未给板块代码时，先用 `plate-list` 找到代码；
   members/platek/platetrend 的板块代码（如 994612）属未知段位，
   但板块子命令固定 market=44 直传网关，**不需要也不做标的解析**。

## 错误语义（退出码表）

| 退出码 | 语义 | stdout | 处理建议 |
|---|---|---|---|
| 0 | 成功 | `{"data": ..., "meta": {"count": N}}` | 直接使用数据 |
| 2 | 未找到标的 / 网关无数据 | `{"error": {"kind": "not_found", ...}}` | 换代码或名称重试，可先 resolve |
| 3 | 歧义 | `{"candidates": [...], "hint": "多个候选，请指定"}` | 向用户列出候选反问，选定后带 sh/sz/bj 前缀重试 |
| 4 | 网关/配置/网络错误 | `{"error": {"kind": "config/network/gateway/...", "message", "actionable"}}` | 按 actionable 排查（KLINE_API_BASE_URL、网络）后重试 |

注：argparse 用法错误（缺参数/非法选项）也走 exit 2，但 stderr 有 usage 文本、stdout 无 JSON——与 not_found 靠 stdout 是否有 JSON 区分。

## 安全铁律

- **只读 GET**：全部请求均为 `GET {KLINE_API_BASE_URL}/reqxml` 查询，无任何写操作。
- **限流铁律**：对网关请求间隔 **≥0.1s**（库内进程级共享限流自动保证）；
  不要绕过库并发刷网关，也不要多进程并行狂拉。
- **按需拉取**：优先给明确的 `--count/--begin/--end` 而非默认全量
  （默认 dayk -120 / mink -240）；板块列表默认每类 30，确需全量再 `--full`；
  成份股默认前 50，确需全量再 `--all`；市场个股排行默认前30且单次最多100，
  不主动跨页抓取全市场。
- **不复用超过当日的数据**：行情不是历史事实，分时/分钟K/快照随盘变化；
  跨日引用必须重新拉取，缓存至多当日有效。
