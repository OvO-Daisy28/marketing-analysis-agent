# 运行与故障排查

[项目首页](../README.md) · [文档导航](README.md) · [当前架构](architecture.md) · [接口说明](api.md)

本页说明当前可运行版本。远程受控试用的新增设计见[方案报告](solution-analysis.md#target-design)。

## 启动

需要 Python 3.12/3.13、[uv](https://docs.astral.sh/uv/)、Node.js 24。正式部署使用 PostgreSQL；本地单 Worker 体验允许 SQLite。

### Docker Compose

```sh
cp .env.example .env
# 模拟体验保留 MODEL_MODE=mock；真实模型填写 LLM_* 并设 MODEL_MODE=live。
docker compose up --build -d
```

打开 <http://localhost:8000>，先查看案例，点击“创建自己的分析”进入工作区。Compose 先迁移数据库、导入数据，然后启动 API 与 Worker；默认仅绑定本机端口。数据库密码可通过 `POSTGRES_PASSWORD` 修改。

### 本地开发

```sh
uv sync --frozen
cp .env.example .env
# 无 PostgreSQL 时将 DATABASE_URL 改为 sqlite:///./data/local.db
uv run python -m marketing.cli init-db
uv run python -m marketing.cli import-data
cd web
npm ci
npm run build
cd ..
```

分别在两个终端运行：

```sh
uv run uvicorn marketing.api:app --host 127.0.0.1 --port 8000
uv run python -m marketing.worker
```

Windows 可使用 `./start.ps1` 完成初始化与后台启动，使用 `./stop.ps1` 关闭该脚本启动的进程。脚本不覆盖已有 `.env`。

API 文档：<http://localhost:8000/docs>，页面资源由本地服务提供，无需访问外部 CDN。启动脚本在 API、文档页就绪且 Worker 仍运行后才报告成功；关闭终端或重启电脑后，若服务未运行，需要重新执行 `./start.ps1`。前端开发服务使用 `npm run dev`，此时将 `APP_ORIGIN` 设置成实际 Vite 地址，并重启 API。

## 模型配置

```dotenv
MODEL_MODE=live
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-id
LLM_API_KEY=your-private-key
```

支持 OpenAI 风格的非流式 Chat Completions 工具调用。UI 的 SSE 展示执行事件，不宣称提供模型 Token 流。模型字段由你的服务供应商决定。

某些兼容网关返回 `{}{...}` 形式的工具参数。只有确实观察到该行为时，启用 `TOOL_ARGUMENTS_EMPTY_PREFIX_FIX=true`；它仅删除多余的前导空对象，并记录原参数及修正事件，不做一般性的 JSON 猜测修复。默认关闭。

`.env`、运行数据库、完整轨迹和下载文件均在 Git 忽略范围中。请勿提交密钥。


## 生命周期

启动前执行 Alembic 迁移和数据导入。导入以 CSV 哈希去重，重复导入同一文件不会增加会话。API 与 Worker 独立运行，创建任务后即使关闭浏览器仍可执行。

查看 /api/health 确认 live 或 mock 模式。没有模型密钥时保持 mock；live 配置错误会以 MODEL_NOT_CONFIGURED 结束，不偷偷切换模拟结果。

## 常见问题

| 表现 | 检查 |
|---|---|
| localhost:8000 拒绝连接 | 在项目根目录运行 `./start.ps1`，等待 ready；查看 `data/api-error.log`，服务需保持运行 |
| /docs 空白 | 文档资源已改为本地 `/docs-assets/`；执行 `uv sync --frozen` 并重启，检查 `/openapi.json` 和资源请求 |
| 一直等待执行 | Worker 是否启动、是否连接同一数据库 |
| 登录后写入 403 | 浏览器 Origin 与 APP_ORIGIN 是否一致，CSRF 是否来自当前会话 |
| 图表不出现 | 浏览器 Console、父页面接口 Network、report-error 事件 |
| 工具参数非法 | 展开执行事件，检查工具名与 arguments；网关多余空对象前缀需显式兼容开关 |
| 达到 TOKEN_BUDGET | 查看重复查询、剩余预算和证据读取量，不直接无上限增加预算 |
| 研究后报告结论待更新 | 筛选范围变化；续接分析或交付只含新数据的报告 |
| 服务重启后恢复较慢 | Worker 需等待旧租约到期，默认 120 秒 |
| 模型请求超时 | 最多重试 2 次；用量未知时保留预留 Token，记录可能重复计费 |

## 部署边界

Compose 仅绑定 127.0.0.1。对外部署前需配置 TLS 反向代理、COOKIE_SECURE=true、准确的 APP_ORIGIN、访问策略和数据库备份。首版注册为个人独立工作区，不含团队邀请或企业 SSO。登录限流是进程内保护，不能代替共享网关限流。

SSE 是任务事件流，不是模型 Token 流。GET 订阅不会推进任务，断线后使用事件 ID 继续读取。会话失效后订阅结束。

## 数据备份

PostgreSQL 保存目标、运行、证据、报表快照和会话。部署备份使用数据库原生工具，验证恢复后再扩大使用范围。下载的 CSV 可重新获取，但应核对哈希；不可仅备份前端构建产物。

## 公开仓库发布

只提交独立项目目录。检查 git diff --cached、Git 忽略规则、许可证和已公开评测产物。禁止提交 .env、数据库、私人账号信息或原公司材料。发布脚本只从本机已有 GitHub 登录读取目标服务凭据，不将凭据写入 remote URL。
