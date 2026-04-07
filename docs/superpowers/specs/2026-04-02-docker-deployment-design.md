# Docker Deployment Design

**Date:** 2026-04-02

**Goal**

为 `news-push` 补齐最小可部署的 Docker 运行资产，使项目可以在用户自有服务器上通过 `docker compose` 稳定运行，并保留发送状态文件，避免容器重建后重复推送。

**Scope**

本次只覆盖单服务部署所需的本地资产：

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- README 中的 Docker 部署说明

不包含：

- CI/CD 工作流
- 镜像自动发布
- 反向代理配置
- 监控、告警、日志采集系统

**Current State**

- 应用入口已经可用于容器运行：`python -m news_push`
- HTTP 服务监听 `0.0.0.0:8000`
- 运行时通过环境变量读取配置
- 已发送状态通过 `STATE_FILE` 持久化到本地文件
- 仓库中当前没有任何 Docker 相关文件

**Constraints**

- 运行方式以 `docker compose` 为主，而不是单独的 `docker run`
- 容器必须能通过环境变量注入 `WECOM_WEBHOOK_URL`、`NEWS_IMAGE_BASE_URL`、`STATE_FILE`、`TZ`
- 状态文件必须挂载到宿主机目录持久化
- 容器镜像应尽量简单，不引入额外进程管理器
- 不修改现有业务逻辑和调度策略

**Recommended Approach**

采用单容器方案：

- 基础镜像使用 `python:3.12-slim`
- 在镜像构建阶段安装项目运行依赖并安装当前项目
- 容器启动命令直接运行 `python -m news_push`
- `docker-compose.yml` 负责注入环境变量、暴露端口、挂载状态目录和配置重启策略

推荐这个方案的原因：

- 与现有代码入口完全一致，改动最小
- 运维面简单，没有多容器依赖
- `docker compose` 便于长期维护环境变量和宿主机挂载

**Alternatives Considered**

方案 1：在容器中继续使用 `uv run`

- 优点：和本地开发命令一致
- 缺点：镜像里额外引入 `uv`，启动路径更重，不是生产必须

方案 2：增加 Nginx 或进程守护层

- 优点：可以扩展更多运维能力
- 缺点：对当前单服务场景属于过度设计

本次不采用以上两种方案。

**File-Level Design**

`Dockerfile`

- 使用 `python:3.12-slim`
- 设置工作目录
- 先复制 `pyproject.toml` 和 `uv.lock` 以利用构建缓存
- 安装项目运行依赖
- 复制 `src/` 与必要文档
- 使用非 root 用户运行
- 暴露 `8000`
- 启动命令为 `python -m news_push`

`.dockerignore`

- 忽略开发与本地产物：
  - `.venv/`
  - `.pytest_cache/`
  - `__pycache__/`
  - `.mypy_cache/`
  - `.ruff_cache/`
  - `.tox/`
  - `.codex/`
  - `.idea/`
  - `.vscode/`
  - `dist/`
  - `build/`
  - `*.egg-info/`
  - `.env*`
  - `docs/` 以外的非运行必需内容视情况控制

`docker-compose.yml`

- 定义单个服务 `news-push`
- 使用本地 `Dockerfile` 构建镜像
- 端口映射 `8000:8000`
- 通过环境变量设置：
  - `WECOM_WEBHOOK_URL`
  - `NEWS_IMAGE_BASE_URL`
  - `STATE_FILE=/data/state.json`
  - `TZ=Asia/Shanghai`
- 挂载宿主机目录到容器 `/data`
- 设置 `restart: unless-stopped`
- 添加基础健康检查，请求 `/health`

`README.md`

- 增加 Docker 部署章节
- 说明如何准备环境变量
- 说明如何创建持久化目录
- 提供 `docker compose up -d --build`
- 提供验活命令：
  - `curl /health`
  - `curl /status`
  - `curl -X POST /jobs/news-image/run`
  - `curl -X POST /jobs/oil/run`

**Runtime Data Design**

- 容器内统一使用 `/data/state.json` 作为 `STATE_FILE`
- 宿主机挂载目录由用户自行选择，例如 `./data:/data`
- 状态文件属于业务幂等核心数据，必须保留

**Operational Notes**

- `WECOM_WEBHOOK_URL` 为空时，服务虽然能启动，但两个手动接口会返回 `missing_webhook`
- `jobs/oil/run` 在非调价日返回 `not_adjustment_day` 属于正常行为
- 由于仓库当前只包含 `oil_calendar_2026.json`，进入 2027 年前需要补充新的年度调价日文件

**Testing Plan**

实现后至少验证：

- 镜像可以成功构建
- `docker compose up -d` 后容器正常启动
- `GET /health` 返回 200
- `GET /status` 返回已注册任务
- 挂载目录下能生成并更新 `state.json`
- 手动触发 `POST /jobs/news-image/run` 在图片存在时返回 `sent`

**Success Criteria**

- 用户可在服务器上通过单条 `docker compose up -d --build` 启动服务
- 状态文件持久化到宿主机
- 服务重启后不会丢失已发送记录
- README 提供足够完整的部署和验活说明
