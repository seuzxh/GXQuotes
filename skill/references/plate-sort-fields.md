# 板块与成份股排序字段

在用户要求行业/概念/地域/风格板块排行，或指定板块的成份股排行，且需要确定
`plate-list --sort` / `members --sort` 字段时读取。

- `plate-list` 每条板块数据固定返回下表全部 27 个字段。
- `members` 保持紧凑快照结构，并追加当前排序字段的具名值。
- 网关缺失值输出为 `null`，两者都不使用通用 `sort_value`。
- 价格类在 `plate-list` 中是板块指数点位，在 `members` 中是股票价格（元）。
- 43完整分时数组、560连板字符串、60/61/62板块涨跌平家数及189交易分钟数
  不属于成份股普通数值排序字段，不向Agent开放。

| `--sort` | 属性 ID | 中文含义 | 输出字段 | 单位 |
|---|---:|---|---|---|
| `price` | 10 | 最新点位 | `price` | 点 |
| `change` | 510 | 涨跌 | `change` | 点 |
| `change_pct` | 514 | 涨跌幅 | `change_pct` | % |
| `change_speed_3m_pct` | 573 | 3分钟涨速 | `change_speed_3m_pct` | % |
| `previous_close` | 4 | 昨收 | `previous_close` | 点 |
| `previous_change_pct` | 575 | 昨日涨跌幅 | `previous_change_pct` | % |
| `open` | 5 | 今开 | `open` | 点 |
| `open_change_pct` | 574 | 开盘涨跌幅 | `open_change_pct` | % |
| `high` | 6 | 最高 | `high` | 点 |
| `high_change_pct` | 576 | 最高涨跌幅 | `high_change_pct` | % |
| `low` | 7 | 最低 | `low` | 点 |
| `low_change_pct` | 577 | 最低涨跌幅 | `low_change_pct` | % |
| `volume` | 12 | 总成交量 | `volume` | 股 |
| `amount` | 13 | 总成交额 | `amount` | 元 |
| `last_volume` | 21 | 现手 | `last_volume` | 股 |
| `turnover_rate` | 551 | 换手率 | `turnover_rate` | % |
| `amplitude` | 513 | 振幅 | `amplitude` | % |
| `volume_ratio` | 521 | 量比 | `volume_ratio` | 倍 |
| `inside_volume` | 23 | 内盘 | `inside_volume` | 股 |
| `change_pct_3d` | 751 | 3日涨幅 | `change_pct_3d` | % |
| `change_pct_5d` | 752 | 5日涨幅 | `change_pct_5d` | % |
| `change_pct_10d` | 753 | 10日涨幅 | `change_pct_10d` | % |
| `change_pct_20d` | 754 | 20日涨幅 | `change_pct_20d` | % |
| `change_pct_60d` | 755 | 60日涨幅 | `change_pct_60d` | % |
| `change_pct_120d` | 756 | 120日涨幅 | `change_pct_120d` | % |
| `change_pct_250d` | 757 | 250日涨幅 | `change_pct_250d` | % |
| `reference_price` | 11 | 报价基准价 | `reference_price` | 点 |

## 方向和意图映射

- `--direction desc`：从大到小，适用于“最高/最大/最强/最快/排行前列”。
- `--direction asc`：从小到大，适用于“最低/最小/最弱/跌幅最大”。
- “涨幅榜”→ `change_pct desc`；“跌幅榜”→ `change_pct asc`。
- “成交额/成交量/换手率/量比最高”分别映射到
  `amount/volume/turnover_rate/volume_ratio desc`。
- “N日涨幅”映射到对应 `change_pct_Nd`；未指定方向时默认 `desc`。

`plate-list --type all` 会让四类板块分别按同一字段和方向排序后再合并，
不是四类板块的全局混合排行。

`members` 的自然语言示例：

- “AI芯片板块涨幅前30只” → `members 994612 --sort change_pct --direction desc --limit 30`
- “成交额最高的成份股” → `members <板块代码> --sort amount --direction desc`
- “跌幅最大的成份股” → `members <板块代码> --sort change_pct --direction asc`
