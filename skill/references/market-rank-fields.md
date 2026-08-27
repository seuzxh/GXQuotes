# 市场个股排行

在用户要求全A股、沪深A股、沪市、深市、北交所、沪深主板或创业板的个股排行时，
用于确定 `market-rank --scope/--sort/--direction`。

## 市场范围

| `--scope` | 证券池 | `markettype` | `routemarkets` |
|---|---|---|---|
| `all-a` | 京沪深A股 | `JHSASH` | `0,1,103` |
| `hs-a` | 沪深A股 | `HSASH` | `0,1` |
| `sh-a` | 上证A股 | `SHASH` | `1` |
| `sz-a` | 深证A股 | `SZASH` | `0` |
| `bj-a` | 北证A股 | `BJASH` | `103` |
| `main` | 沪深主板 | `HSMAIN` | `0,1` |
| `gem` | 创业板 | `SZGEM` | `0` |

`markettype` 是逻辑证券池，`routemarkets` 是物理市场路由；脚本已固定经过真实请求
验证的组合，Agent 不应自行拆开重组。

## 排序字段

下列字段已通过 Action=10006 的升序和降序真实请求验证。每条结果固定返回全部字段，
缺失值为 `null`；价格为元、成交额为元、成交量为股、百分比直接以 `%` 数值表示。

| `--sort` | 属性ID | 中文含义 | 输出字段 | 单位 |
|---|---:|---|---|---|
| `price` | 10 | 最新价 | `price` | 元 |
| `change` | 510 | 涨跌额 | `change` | 元 |
| `change_pct` | 514 | 涨跌幅 | `change_pct` | % |
| `change_speed_3m_pct` | 573 | 3分钟涨速 | `change_speed_3m_pct` | % |
| `previous_close` | 4 | 昨收 | `previous_close` | 元 |
| `previous_change_pct` | 575 | 昨日涨跌幅 | `previous_change_pct` | % |
| `open` | 5 | 今开 | `open` | 元 |
| `open_change_pct` | 574 | 开盘涨跌幅 | `open_change_pct` | % |
| `high` | 6 | 最高价 | `high` | 元 |
| `high_change_pct` | 576 | 最高涨跌幅 | `high_change_pct` | % |
| `low` | 7 | 最低价 | `low` | 元 |
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
| `reference_price` | 11 | 报价基准价 | `reference_price` | 元 |
| `order_ratio` | 511 | 委比 | `order_ratio` | % |
| `order_diff` | 512 | 委差 | `order_diff` | 股 |
| `outside_volume` | 22 | 外盘 | `outside_volume` | 股 |

## 意图映射

- “涨幅最高/涨幅榜” → `change_pct desc`。
- “跌幅最大/跌幅榜” → `change_pct asc`。
- “涨幅前N只个股/股票”“跌幅前N只个股/股票”即使不含“排行/榜”，仍路由到
  `market-rank`，并使用 `--limit N`。
- “成交额/成交量/换手率/量比最高” → 对应字段 `desc`。
- “委比最高/最低” → `order_ratio desc/asc`。
- “N日涨幅” → 对应 `change_pct_Nd`。
- 未指定证券池时，“股票/个股排行”默认 `all-a`；若用户明确说沪深A股，则用 `hs-a`。

10006默认证券池不排除新股、ST或风险警示股票。同值并列项没有稳定二级排序；
`retrieved_at` 是客户端请求完成时间，行情随市场变化，跨日必须重新查询。
