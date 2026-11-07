# 六仙出林 · 林部选基看板

大鹅基金林部（基金定投）的六风格选基看板：成长、趋势、质量、价值、主题、海外各选一只。

- `scripts/fetch.py`：从天天基金/东方财富 F10 和 TradingView 抓取公开数据（原始数据不入库）
- `scripts/build.py`：四关筛选、打分、组合体检、波动率倒数加权，输出 `data/latest.json`；正式名单 `data/official.json` 每季度调仓
- `config.json`：阈值与调仓参数
- GitHub Actions 每周五北京时间 17:00 更新

仅为个人研究工具，不构成投资建议；仓库不含任何持仓、账户或密钥。
