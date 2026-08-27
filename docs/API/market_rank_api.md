# Action 10006 市场个股排行接口

`tzt_api.market_rank.MarketRankFetcher` 封装中焯行情 3.0 的 `Action=10006`，用于在
指定证券池内按行情字段做服务端排序。它查询的是**个股排行**；板块排行使用10007，
某板块成份股排行使用10005。

## Python 用法

```python
from tzt_api import MarketRankFetcher

fetcher = MarketRankFetcher()
rows = fetcher.get_market_rank(
    scope="all_a",
    start=0,
    count=30,
    sort_by="change_pct",
    direction="desc",
)
print(fetcher.last_rank_meta)
```

`count` 为1到100，`start` 为非负整数。10006返回实时排行窗口，跨页并非强一致快照，
因此库只提供显式单页请求，不提供自动全量迭代器。

## 证券池

`markettype` 定义逻辑证券池，`routemarkets` 指定物理市场路由；两者相关但不能互相替代。
普通调用方应使用内置 `scope`，避免组合错配。

| scope | markettype | routemarkets | 含义 |
|---|---|---|---|
| `all_a` | `JHSASH` | `0,1,103` | 京沪深A股 |
| `hs_a` | `HSASH` | `0,1` | 沪深A股 |
| `sh_a` | `SHASH` | `1` | 上证A股 |
| `sz_a` | `SZASH` | `0` | 深证A股 |
| `bj_a` | `BJASH` | `103` | 北证A股 |
| `main` | `HSMAIN` | `0,1` | 沪深主板 |
| `gem` | `SZGEM` | `0` | 创业板 |

市场序号为深证0、上证1、北证103。默认证券池由上游市场类型定义，当前不额外排除
新股、ST或风险警示股票。

## 请求映射

封装默认构造不含设备指纹、但固定请求完整33项 props 的请求：

| 参数 | 说明 |
|---|---|
| `Action=10006` | 市场排行功能号 |
| `markettype` | scope 对应逻辑证券池 |
| `routemarkets` | scope 对应市场路由，逗号分隔 |
| `props` | 身份列0/1/2 + 全部30个行情字段 |
| `sort` | `sort_by` 对应属性 ID |
| `direction` | `asc→0`，`desc→1` |
| `start/count` | 单页偏移与数量 |
| `outtype=1` | JSON 输出 |

无需复制真实 App 抓包中的设备指纹、`ReqNo/ReqTag`、`groups`、`900.props`、`Route`、
`rights`、`needtitle` 等参数；当前网关上，上述默认参数集已实测可用。

## 可排序字段与返回单位

每行固定返回 `code/symbol/name/market/market_name` 及下列全部30个字段；缺失字段为
`None`。选择哪个排序字段都不会改变输出 schema。

| sort_by | 属性ID | 含义 | 返回单位 |
|---|---:|---|---|
| `price` | 10 | 最新价 | 元 |
| `change` | 510 | 涨跌额 | 元 |
| `change_pct` | 514 | 涨跌幅 | % |
| `change_speed_3m_pct` | 573 | 3分钟涨速 | % |
| `previous_close` | 4 | 昨收 | 元 |
| `previous_change_pct` | 575 | 昨日涨跌幅 | % |
| `open` | 5 | 今开 | 元 |
| `open_change_pct` | 574 | 开盘涨跌幅 | % |
| `high` | 6 | 最高 | 元 |
| `high_change_pct` | 576 | 最高涨跌幅 | % |
| `low` | 7 | 最低 | 元 |
| `low_change_pct` | 577 | 最低涨跌幅 | % |
| `volume` | 12 | 总成交量 | 股 |
| `amount` | 13 | 总成交额 | 元 |
| `last_volume` | 21 | 现手 | 股 |
| `turnover_rate` | 551 | 换手率 | % |
| `amplitude` | 513 | 振幅 | % |
| `volume_ratio` | 521 | 量比 | 倍 |
| `inside_volume` | 23 | 内盘 | 股 |
| `change_pct_3d` | 751 | 3日涨幅 | % |
| `change_pct_5d` | 752 | 5日涨幅 | % |
| `change_pct_10d` | 753 | 10日涨幅 | % |
| `change_pct_20d` | 754 | 20日涨幅 | % |
| `change_pct_60d` | 755 | 60日涨幅 | % |
| `change_pct_120d` | 756 | 120日涨幅 | % |
| `change_pct_250d` | 757 | 250日涨幅 | % |
| `reference_price` | 11 | 报价基准价 | 元 |
| `order_ratio` | 511 | 委比 | % |
| `order_diff` | 512 | 委差 | 股 |
| `outside_volume` | 22 | 外盘 | 股 |

统一换算规则：价格原值除以1,000,000，金额除以10,000，量保持股，比率与百分比
原值除以1,000。

## Skill 用法

```bash
python skill/scripts/quotes.py market-rank \
  --scope all-a --sort change_pct --direction desc --limit 30
```

Skill 输出 `data` 和 `meta`；`meta` 包含证券池、`markettype/routemarkets`、排序口径、
偏移、命中总量及抓取时间。自然语言中的“当前全A股涨幅前50只股票”应路由到该命令；
“概念板块涨幅前30”应路由到 `plate-list`。

## 验证结论

2026-08-27 对七个内置证券池完成真实请求验证；对全部30个字段分别完成升序与降序
请求、字段非空和单页单调性验证。官方定义仍以
[中焯官方文档](中焯官方文档/README.md)为准，真实网关行为以集成测试定论。
