# Feishu RSS Digest for Alibaba Cloud FC

这是一个部署到阿里云函数计算后，按定时触发器抓取 RSS 并写入飞书多维表的工具。

## 主流程

1. fork 本仓库到你自己的代码仓库
2. 填写仓库根目录的 `先填这个.yml`
3. 在阿里云 FC 控制台通过“代码仓库”创建函数
4. 按下面的参数配置函数
5. 手动创建定时触发器

当前不再使用 `s deploy`、`s.yaml`、`publish.yaml`、仓库导入应用或旧 workflow 路线。

## 配置规则

- 代码优先读取 `先填这个.yml`
- 只有某个字段在 YAML 里留空时，才回退到对应环境变量
- 环境变量只是兜底，不是主入口
- `先填这个.yml` 是模板；真实值建议只存在你自己的私有仓库
- `autoFetchSchedule` 只是兼容字段，不控制实际运行频率

字段映射：

- `feishuAppId` -> `FEISHU_APP_ID`
- `feishuAppSecret` -> `FEISHU_APP_SECRET`
- `newsTableLink` -> `FEISHU_NEWS_TABLE_LINK`
- `rssTableLink` -> `FEISHU_RSS_TABLE_LINK`
- `promptDocLink` -> `FEISHU_PROMPT_DOC_LINK`
- `modelApiKey` -> `NVIDIA_API_KEY`

其中 `modelApiKey` 当前实际对应的是 `NVIDIA API Key`。

## FC 创建参数

- 地域：`ap-southeast-1`
- 运行环境：`Python 3.10`
- 代码路径：`.`
- 函数入口：`rss_ingest.handler`
- 执行时长：`600`
- 构建命令：`pip install -r requirements.txt -t .`
- 触发器类型：定时触发器异步调用
- 推荐 Cron：`0 0 * * * *`

当前真正生效的运行频率，以阿里云 FC 控制台里的定时触发器为准。

## 飞书表结构

这个项目依赖固定字段 schema，字段名必须与代码一致。

新闻表至少需要：

- `标题`
- `AI打分`
- `分类`
- `总结`
- `发布时间`
- `来源`
- `全文`
- `item_key`
- `创建时间`

RSS 源表至少需要：

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

Prompt 文档需要提供可被飞书 docx raw content API 读取的文档链接。

## 安全说明

- 仓库里的 `先填这个.yml` 只保留空模板，不应保留任何真实密钥、真实链接或真实 token
- 如果你曾在任何仓库、分支或提交里提交过真实密钥，必须全部轮换
- 请不要把填了真实值的 `先填这个.yml` 提交回公共上游仓库

## 仍需手动完成

- 在自己的仓库里填写真实配置
- 在 FC 控制台选择代码仓库并完成首次构建
- 手动创建定时触发器
- 确保函数具备外网访问能力
- 按需查看运行日志排查飞书权限、RSS 可访问性和 NVIDIA API 问题
