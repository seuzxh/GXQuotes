---
name: gxquotes
description: >
  A股行情数据技能：日K/分钟K（前/后/不复权 + 复权因子）、实时与历史分时、个股与
  主要指数、概念板块归属/成份股/板块指数行情（日K + 分钟K + 分时）。触发词：行情、
  K线、分时、复权、指数、概念板块、成份股、板块。数据口径：价格/成交额=元、
  成交量=股、涨跌幅=%。
---

# 行情 Skill（gxquotes）

统一入口 `skill/scripts/quotes.py`：**stdout 输出 JSON**（`ensure_ascii=False, indent=2`），
日志走 stderr；退出码表达语义（见下方退出码表）。所有请求均为只读 GET。

## 环境要求

- 环境变量 `KLINE_API_BASE_URL`（必配，行情网关地址）。未配置时脚本 exit 4，
  `error.message` 附配置指引。配置方式：
  `export KLINE_API_BASE_URL="http://183.242.5.14:7778"`
  （或写入 `tzt_api/config/kline_config.yaml` 的 `api.base_url`）
- Python ≥3.9 + tzt-api v2.0.0（依赖仅 requests + PyYAML）。
  在 GXQuotes 仓库内直接运行即可（脚本自动把仓库根加入 `sys.path`）；
  仓库外使用需先 `pip install -e <本仓库>`

## 单位口径（全部子命令统一）

- 价格（open/high/low/close/price）：**元**（板块指数为点，均已由库换算）
- 成交额（amount/turnover）：**元**
- 成交量（volume）：**股**（非手）
- 涨跌幅（change_pct）：**%**

## 八个子命令（示例均可直接运行）

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

### 5. plates — 个股所属板块

```bash
python skill/scripts/quotes.py plates sh600519 --type concept
```

exit 0 → `{"data": [{"code","name","market","type":"concept|industry|region"}], ...}`

- `--type concept|industry|region`：过滤；缺省返回全部并带 `type` 字段

### 6. members — 板块成份股

```bash
python skill/scripts/quotes.py members 994612
```

exit 0 → `{"data": [{"code","name","market","price","change","change_pct","high","low"}], ...}`

- 默认前 50 只（已剔除板块自身占位行）；`--all` 自动翻页拉取全量

### 7. platek — 板块指数K线

```bash
python skill/scripts/quotes.py platek 994612 --freq 5min --count -3
```

exit 0 → 分钟K（结构同 mink，带 `time` 字段）。不给 `--freq` 则为日K（结构同 dayk，缺省 -120 根）。

### 8. platetrend — 板块指数分时

```bash
python skill/scripts/quotes.py platetrend 994612
```

exit 0 → 结构同 trend（`market_date/pre_market/trading`）；`--date YYYYMMDD` 取历史。

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
4. **板块代码直传**：members/platek/platetrend 的板块代码（如 994612）属未知段位，
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
  （默认 dayk -120 / mink -240）；成份股默认前 50，确需全量再 `--all`。
- **不复用超过当日的数据**：行情不是历史事实，分时/分钟K/快照随盘变化；
  跨日引用必须重新拉取，缓存至多当日有效。
