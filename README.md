# news-push

独立的 Python 推送服务，使用 `FastAPI + APScheduler + httpx`。

这个服务只保留两条推送链路：

- 图片新闻推送：轮询 `news-data` 生成的日报图片，使用企业微信机器人发送图片消息
- 油价推送：抓取四川发改委成品油价格公告，解析附件后发送文本消息

## 功能说明

### 1. 图片新闻推送

- 检查地址模板：`https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images/YYYY-MM-DD.png`
- 调度时间：每天 `00:00-10:59`，每 10 分钟检查一次
- 推送规则：
  - 如果当天图片存在，则发送企业微信图片消息
  - 如果当天已经发送过，则不再重复发送
  - 如果图片不存在，则等待下次调度继续检查

### 2. 油价推送

- 数据来源：`https://fgw.sc.gov.cn/sfgw/tzgg/olist.shtml`
- 调度时间：每天 `17:00-20:59`，每 30 分钟检查一次
- 推送规则：
  - 先检查仓库内维护的成品油调价窗口日 JSON
  - 只有命中调价窗口日当天才会抓取四川发改委公告
  - 只处理当天发布的“成品油价格”公告
  - 找到公告详情页中的 `.docx` 附件后解析油价表格
  - 当天发送成功后不再重复发送

## 技术栈

- `FastAPI`：提供健康检查、状态查询、手动触发接口
- `APScheduler`：注册和执行定时任务
- `httpx`：拉取新闻图片、网页和企业微信 webhook
- `python-docx`：解析油价公告中的 Word 附件
- `beautifulsoup4`：解析四川发改委页面结构

## 项目结构

```text
src/news_push/
  __main__.py      本地启动入口
  app.py           FastAPI 应用与调度器入口
  config.py        环境变量配置
  http.py          带重试的 HTTP 调用封装
  news_image.py    图片新闻轮询与推送逻辑
  oil.py           油价公告抓取与解析逻辑
  oil_calendar.py  油价调价窗口日生成逻辑
  state.py         已发送状态持久化
  wecom.py         企业微信机器人消息发送

tests/
  test_app.py
  test_news_image_service.py
  test_oil_calendar_generator.py
  test_oil_service.py
  test_state_store.py
  test_wecom.py

scripts/
  generate_oil_calendar.py
```

## 环境变量

服务通过环境变量读取配置，尤其是 `WECOM_WEBHOOK_URL`，不要写死在代码或仓库文件里。

可用环境变量如下：

- `WECOM_WEBHOOK_URL`
  - 必填
  - 企业微信机器人 webhook 地址
- `NEWS_IMAGE_BASE_URL`
  - 选填
  - 默认值：`https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images`
- `STATE_FILE`
  - 选填
  - 默认值：`/tmp/news-push/state.db`
  - SQLite 状态库文件，用于记录“当天是否已发送”
  - 生产环境建议挂载到持久化目录
- `TZ`
  - 选填
  - 默认值：`Asia/Shanghai`

示例见 [`./.env.example`](./.env.example)。本地运行时也可以直接在 shell 中导出环境变量。

## 本地运行

### 1. 安装依赖

```bash
uv sync --extra dev
```

### 2. 启动服务

```bash
uv run --project . python -m news_push
```

默认监听：

```text
http://0.0.0.0:8000
```

如需只在本机访问，可自行把 [`src/news_push/__main__.py`](./src/news_push/__main__.py) 中的监听地址改为 `127.0.0.1`。

### 3. 带环境变量启动

```bash
WECOM_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key' \
NEWS_IMAGE_BASE_URL='https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images' \
STATE_FILE='/tmp/news-push/state.db' \
TZ='Asia/Shanghai' \
uv run --project . python -m news_push
```

### 4. 生成当年油价调价日 JSON

```bash
uv run --project . python scripts/generate_oil_calendar.py
```

运行时会按当前年份生成 `src/news_push/data/oil_calendar_<year>.json`，如果文件已存在会直接覆盖，同时把生成出的 JSON 打印到标准输出。

## Docker 部署

推荐使用仓库根目录自带的 `docker-compose.yml` 部署。

默认配置只会把服务绑定到宿主机 `127.0.0.1:8000`，适合配合 Nginx、Caddy 或 SSH 隧道访问，避免把手动触发接口直接暴露到公网。

### 1. 服务器首次部署

下面以 Ubuntu 服务器为例，假设项目目录放在 `/opt/news-push`。

安装 Docker 和 Compose：

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2
service docker start
```

拉取项目代码：

```bash
mkdir -p /opt
cd /opt
git clone <your-repo-url> news-push
cd /opt/news-push
```

用真实 webhook 直接启动：

```bash
WECOM_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key' \
bash scripts/deploy_docker.sh
```

部署完成后检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/status
docker compose ps
docker compose logs -f
```

### 2. 准备环境变量

可以直接复制示例文件：

```bash
cp .env.example .env
```

然后至少填写企业微信 webhook：

```dotenv
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key
```

可选变量：

- `NEWS_IMAGE_BASE_URL`
- `TZ`

`STATE_FILE` 在 Compose 中已固定为容器内 `/data/state.db`，不用单独写到 `.env`。

### 3. 准备持久化目录

```bash
mkdir -p data
```

Compose 会把宿主机的 `./data` 挂载到容器内 `/data`，用于保存 SQLite 状态库，避免容器重建后重复推送。

### 4. 构建并启动

```bash
docker compose up -d --build
```

也可以直接使用仓库自带脚本：

```bash
bash scripts/deploy_docker.sh
```

如果你想一次性传入真实 webhook 并生成或更新 `.env`：

```bash
WECOM_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key' \
bash scripts/deploy_docker.sh
```

查看运行日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

更新服务：

```bash
git pull
docker compose up -d --build
```

### 5. 验活

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

查看任务状态：

```bash
curl http://127.0.0.1:8000/status
```

手动触发图片新闻检查：

```bash
curl -X POST http://127.0.0.1:8000/jobs/news-image/run
```

手动触发油价检查：

```bash
curl -X POST http://127.0.0.1:8000/jobs/oil/run
```

### 6. 运行说明

- `./data/state.db` 是幂等控制的核心状态库文件，不能随意删除
- `scripts/deploy_docker.sh` 会自动创建 `./data` 目录，并在每次执行时用当前 shell 环境补全或更新 `.env`
- 如果需要对外开放接口，建议放在反向代理后面并自行补访问控制，不要直接改成公网裸露端口
- 升级前建议先备份 `./data/state.db`
- 如果升级后需要回滚，先切回旧代码版本，再执行 `docker compose up -d --build`
- `POST /jobs/oil/run` 在非调价窗口日返回 `not_adjustment_day` 属于正常行为
- 进入 2027 年前，需要补充新的油价调价日 JSON，否则油价任务不会命中新年度日期
- `WECOM_WEBHOOK_URL` 未配置时，服务能启动，但两个手动触发接口会返回 `missing_webhook`

## HTTP 接口

### `GET /health`

健康检查。

示例响应：

```json
{
  "status": "ok"
}
```

### `GET /status`

查看当前已注册任务和发送状态快照。

示例响应：

```json
{
  "jobs": [
    "news_image_push",
    "oil_price_push"
  ],
  "state": {
    "news_image": {
      "2026-03-30": {
        "url": "https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images/2026-03-30.png"
      }
    }
  },
  "webhookConfigured": true
}
```

### `POST /jobs/news-image/run`

手动执行一次图片新闻检查。

适合：

- 验证图片 URL 是否可用
- 部署后手动试发
- 排查调度问题

### `POST /jobs/oil/run`

手动执行一次油价检查。

适合：

- 验证油价解析逻辑
- 手动补发当天油价消息

## 状态持久化

服务通过 `STATE_FILE` 指向的 SQLite 文件保存已发送记录，避免重复推送。

逻辑上的状态内容按通道和日期组织，等价于下面这类结构：

```json
{
  "news_image": {
    "2026-03-30": {
      "url": "https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images/2026-03-30.png"
    }
  },
  "oil_price": {
    "2026-03-30": {
      "title": "成品油价格按机制上调",
      "page_url": "https://fgw.sc.gov.cn/sfgw/tzgg/2026/3/30/abcd.shtml"
    }
  }
}
```

建议：

- 开发环境可直接用默认 `/tmp/news-push/state.db`
- 生产环境务必将 `STATE_FILE` 指向挂载卷或宿主机目录

## 测试

运行测试：

```bash
uv run --project . pytest
```

如果只想跑单个测试文件：

```bash
uv run --project . pytest tests/test_app.py
```

## 首次部署检查清单

建议第一次部署时按下面顺序检查。

### 1. 配置环境变量

确认 `.env` 或容器环境变量至少包含：

- `WECOM_WEBHOOK_URL`
- `STATE_FILE`
- `TZ`

然后按你的实际运行方式导出环境变量，填入真实的企业微信 webhook。

### 2. 启动服务

```bash
WECOM_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key' \
NEWS_IMAGE_BASE_URL='https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images' \
STATE_FILE='/tmp/news-push/state.db' \
TZ='Asia/Shanghai' \
uv run --project . python -m news_push
```

### 3. 检查健康状态

```bash
curl http://127.0.0.1:8000/health
```

期望返回：

```json
{
  "status": "ok"
}
```

### 4. 检查调度任务是否注册成功

```bash
curl http://127.0.0.1:8000/status
```

重点确认：

- `webhookConfigured` 为 `true`
- `jobs` 中包含 `news_image_push`
- `jobs` 中包含 `oil_price_push`

### 5. 验证状态库文件是否可写

如果你把 `STATE_FILE` 指到项目目录或其他持久化目录，例如：

```text
./data/state.db
```

第一次启动时文件可能还不存在；首次发送成功后应自动生成。

### 6. 手动触发图片新闻检查

```bash
curl -X POST http://127.0.0.1:8000/jobs/news-image/run
```

常见返回：

- `{"sent": true, "reason": "sent"}`：成功发送
- `{"sent": false, "reason": "image_missing"}`：当天图片还未生成
- `{"sent": false, "reason": "already_sent"}`：当天已发送
- `{"sent": false, "reason": "missing_webhook"}`：未配置 webhook

### 7. 手动触发油价检查

```bash
curl -X POST http://127.0.0.1:8000/jobs/oil/run
```

常见返回：

- `{"sent": true, "reason": "sent"}`：成功发送
- `{"sent": false, "reason": "listing_missing"}`：当天没有匹配公告
- `{"sent": false, "reason": "attachment_missing"}`：公告存在但未找到附件
- `{"sent": false, "reason": "price_missing"}`：附件解析后没有有效价格数据
- `{"sent": false, "reason": "already_sent"}`：当天已发送
- `{"sent": false, "reason": "missing_webhook"}`：未配置 webhook

### 8. 检查企业微信实际到达情况

确认企业微信群机器人是否收到：

- 图片新闻图片消息
- 油价文本消息

如果接口返回成功但群内未收到，优先检查：

- webhook 是否填错
- 企业微信机器人是否被删除或禁用
- 发送内容是否触发机器人限制

### 9. 重启后验证幂等性

重启服务后再次访问：

```bash
curl http://127.0.0.1:8000/status
```

确认历史发送记录仍在，避免同一天重复推送。

当前测试覆盖：

- 状态持久化读写
- 企业微信图片消息体生成
- 图片新闻轮询发送与去重
- 油价附件地址拼接和推送流程

## 当前限制

- 企业微信目前只接入了机器人 webhook，没有做更复杂的鉴权封装
- 油价公告页面结构如果变更，可能需要更新解析规则
- 当前没有实际联通企业微信和四川发改委站点的集成测试

## License

本项目使用 MIT License，见 [`./LICENSE`](./LICENSE)。

## Contributing

贡献说明见 [`./CONTRIBUTING.md`](./CONTRIBUTING.md)。
