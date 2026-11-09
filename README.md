# 六仙出林 · 林部选基看板

大鹅基金林部（基金定投）的六风格选基看板：成长、趋势、质量、价值、主题、海外各选一只。

- `scripts/fetch.py`：从天天基金/东方财富 F10 和 TradingView 抓取公开数据（原始数据不入库）。主源失败时改用下方备用，不编造行情
- `scripts/build.py`：四关筛选、打分、组合体检、波动率倒数加权，输出 `data/latest.json`；正式名单 `data/official.json` 每季度调仓，并把权重写进每只基金；调仓追加 `data/history.json`
- `scripts/mark_stale.py`：抓取或打分失败时只把 `latest.json` 的 `stale` 标为 true，不改已公布数字
- `scripts/turnover.py`：换手率取 2025 年报，=(8.4.3 买入股票成本总额+卖出股票收入总额)/2 ÷ 资产负债表股票投资期初期末均值；结果缓存 `data/turnover.json`，取不到记"缺换手率"不通过；海外类（QDII）免除换手率关
- 风格稳定关：近 12 季前十大重仓相邻季度平均重合（只数/10）≥50%，阈值据实测分布（中位约 0.65，25% 分位约 0.55）；趋势、海外类免除，趋势类排除量化/指数增强/多因子基金
- `config.json`：阈值与调仓参数
- GitHub Actions 每周五北京时间 17:00 更新

仅为个人研究工具，不构成投资建议；仓库不含任何持仓、账户或密钥。

- 准入剔除名称含持有期、封闭、定开、养老、目标日期及"一年/两年/三年/N个月"等持有期字样的产品

## 纸面成交

信号在信号日收盘后计算，成交按下一交易日开盘（T+1 开盘）计。本看板是开放式基金净值，脚本和页面都没有涨跌停跳过，不另造涨停买不到或跌停卖不出的处理。这里只约定纸面时点，不给出回测收益。

## 数据源与过期

主源是天天基金/东方财富基金 F10 与 TradingView 个股指标。主源失败时：

- 基金排名名单改用 `https://www.1234567.com.cn/data/rankhandler.aspx`（与主源同参数）
- `pingzhongdata` 改用 `https://fund.1234567.com.cn/pingzhongdata/{代码}.js`
- 上述两处都失败时，单只净值日收益率改用 `https://api.fund.eastmoney.com/f10/lsjz` 的 `JZZZL`（空白涨跌幅按主源记 0，不编造净值）。失败只数过多则整次抓取作废，不写入 `raw.json`
- TradingView 失败且本地已有 `data/raw.json` 时，沿用其中的个股指标，并把整份结果标为数据过期；没有缓存则失败退出，不写空行情

最近 A 股交易日取上证指数日 K：主源 `push2his.eastmoney.com`，备用 `91.push2his.eastmoney.com`。净值日期落后于该交易日、沿用了旧个股指标，或没能确认交易日时，`data/latest.json` 写 `stale: true` 和 `stale_reason`。抓取或打分失败时不改已公布数字，由 `scripts/mark_stale.py` 只把 `stale` 设为 true。页面在 `stale` 为真，或净值日期落后于最近交易日（构建时写入的日期，或浏览器能取到的上证指数日期）时，显示「数据过期」。

## 调仓记录

`data/history.json` 在正式调仓写入 `official.json` 时追加一条：日期、调入、调出（代码与名称）、权重、原因/`changes`。种子只收录已经落在 `official.json` 快照里的调仓，调入调出由相邻快照差分得到，不补写没有记录的交易。页面「调仓记录」表读这个文件。

## 权重

波动率倒数权重原本算在 `latest.json` 的 `official.weights`。构建会把同一套权重写进 `official.json` 每只基金的 `weight`，并显示在页面每只基金上。不改 2026Q4 的入选名单。
