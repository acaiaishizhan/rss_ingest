# Feishu RSS Digest for Alibaba Cloud FC

部署到阿里云函数计算 FC 后，按定时触发器抓取 RSS，并写入飞书多维表。

## 当前主流程

1. fork 本仓库到你自己的代码仓库
2. 在阿里云 FC 控制台创建事件函数
3. 上传代码，并确保函数根目录直接包含 `rss_ingest.py`、`config.py`、`feishu_client.py`、`rss_parser.py`、`requirements.txt`
4. 在函数配置里填写环境变量
5. 手动创建定时触发器

## 必填环境变量

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_NEWS_TABLE_LINK`
- `FEISHU_RSS_TABLE_LINK`
- `FEISHU_PROMPT_DOC_LINK`
- `NVIDIA_API_KEY`
- `CUSTOM_API_KEY`（可选）
- `CUSTOM_API_BASE`（可选）
- `CUSTOM_API_MODEL`（可选）

说明：

- `FEISHU_NEWS_TABLE_LINK` 必须是完整的飞书新闻表链接，并包含 `table=` 参数
- `FEISHU_RSS_TABLE_LINK` 必须是完整的飞书 RSS 源表链接，并包含 `table=` 参数
- `FEISHU_PROMPT_DOC_LINK` 必须是可被飞书 docx raw content API 读取的文档链接
- 当前版本只支持 `NVIDIA_API_KEY`

本地调试时可以使用仓库根目录的 `.env`。线上 FC 以函数环境变量为准。

## FC 建议参数

- 地域：`ap-southeast-1`
- 运行环境：`Python 3.10`
- 函数入口：`rss_ingest.handler`
- 执行时长：`600`
- 构建命令：`pip install -r requirements.txt -t .`
- 单实例并发度：`1`

如果控制台默认给出 `index.handler`，请手动改成 `rss_ingest.handler`。

## 触发器

- 触发器类型：定时触发器
- 调用方式：异步调用
- 推荐 Cron：`0 0 * * * *`

实际运行频率以阿里云 FC 控制台中的定时触发器为准。

## 飞书表结构

新闻表至少需要这些字段：

- `标题`
- `AI打分`
- `分类`
- `总结`
- `发布时间`
- `来源`
- `全文`
- `item_key`
- `创建时间`

RSS 源表至少需要这些字段：

- `name`
- `feed_url`
- `enabled`
- `status`
- `last_fetch_time`
- `last_fetch_status`
- `consecutive_fail_count`
- `last_item_guid`
- `last_item_pub_time`
- `item_id_strategy`
- `failed_items`

## 安全说明

- 不要把真实密钥提交到公共仓库
- 如果你曾在任何仓库、分支或提交里提交过真实密钥，必须全部轮换
