# RSS Ingest to Feishu

这是一个 RSS 聚合脚本项目：  
定时抓取多个 RSS 源，用 LLM 做初筛和摘要，然后把结果写入飞书多维表。

## 核心流程

1. 从飞书 RSS 源表读取启用的订阅源。  
2. 抓取并去重文章。  
3. 调用 LLM 输出 `action/score/categories/summary`。  
4. 通过的文章写入新闻表；过滤项可选写入过滤表。  
5. 回写每个 RSS 源的抓取状态。

## 运行方式

- 本地运行：`python rss_ingest.py`
- 函数入口：`rss_ingest.handler`
- GitHub Actions：使用 `.github/workflows/rss-ingest.yml` 定时触发

## 必要环境变量

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_NEWS_TABLE_LINK`
- `FEISHU_RSS_TABLE_LINK`
- `FEISHU_PROMPT_DOC_LINK`
- `NVIDIA_API_KEY`（或 `NVIDIA_API_KEYS`）

常用可选项：

- `AUTO_FETCH_INTERVAL_HOURS`（默认 `3`）
- `LLM_CONCURRENCY`
- `HTTP_TIMEOUT`
- `HTTP_RETRIES`

## 说明

- `.env` 仅用于本地调试，线上请使用平台环境变量（如 GitHub Secrets/Variables）。
- 请不要把真实密钥提交到仓库。
