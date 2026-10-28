# 规宝 v1.0

工程规范智能问答平台（B端），Vue 3 + Vite 前端，Python FastAPI 后端。

## 当前能力

- 自然语言提问，从预构建知识库检索规范条文
- 返回答案、出处（标准/章节/条文/页码）、延伸问题
- Agent 自主规划：LLM Function Calling 决策条文检索、数值计算、规范对比与联网搜索；未配置 LLM 时自动回退规则 Planner
- 多轮记忆：Redis 当前会话窗口 + SQL 原始聊天记录 + LLM 结构化记忆库 + Token 预算控制
- 响应式界面：PC 左侧会话列表 + 右侧聊天，移动端全屏聊天
- 支持上传 PDF 生成可检索的知识文档

## 记忆系统架构（生产版）

记忆链路分为三层，所有原始记录和结构化记忆都以 SQL 为准，Redis 只承担当前会话热缓存：

1. Redis 当前会话：保存最近 `SESSION_KEEP` 条消息，key 为 `memory:session:{user_id}:{conversation_id}`，带 `SESSION_TTL_SECONDS` 过期时间，用于快速组装近期上下文。
2. SQL 原始聊天记录：`conversations`、`messages` 两张表保存会话和每一条用户/助手消息，助手消息附带的来源、推理过程、推荐项等作为 JSON 元数据一并入库。
3. LLM 结构化记忆库：`memory_items` 保存用户级长期记忆（项目地点、建筑类型、规模、偏好、约束条件等），`memory_jobs` 记录提炼任务状态；每次对话结束后在后台异步提炼，失败自动重试一次，LLM 不可用时自动降级为规则抽取。

结构化记忆跨会话共享，因此用户在新会话里提到“防火分区要求”时，系统能自动带上此前记录的“昆山市住宅项目、地上 18 层”等背景。用户维度通过 `X-User-Id` 请求头隔离，正式接入登录后由鉴权中间件注入真实用户 ID 即可。

旧版 `backend/data/memory/*.json` 会在首次启动时自动导入 SQL；不需要可设置 `MEMORY_IMPORT_JSON=0`。

## Function Calling Agent

后端已支持真正的 Function Calling 流程：

```text
用户提问
  -> LLM 收到 tools 列表
  -> LLM 自主决策返回 tool_call
  -> 后端执行 retrieve_standards / calculate_expression / compare_standards
  -> 工具结果回传给 LLM
  -> LLM 生成最终答案
```

默认使用规则 Planner。只有显式关闭稳定回答模式并启用 Function Calling 时，配置了
`LLM_API_BASE` 和 `LLM_API_KEY` 的实例才会走 LLM 工具编排。

```bash
STABLE_ANSWER_MODE=1
AGENT_FUNCTION_CALLING_ENABLED=0
AGENT_MAX_TOOL_TURNS=2
AGENT_LLM_TIMEOUT_SECONDS=20
AGENT_TOOL_RESULT_CHARS=8000
AGENT_LLM_MAX_TOKENS=1200
```

默认开启稳定回答模式。所有规范问答统一使用本地规则 Planner、规范检索和确定性答案生成，
不再根据线上是否配置 LLM 而切换 Function Calling 或建筑类型识别链路。这样可以保证同一个
问题在本地与线上返回相同的结构、规范和依据。

未知俗称为检索漏召回的主要来源。系统增加了一个受限的 LLM 查询扩展层，只在本地词库未命中
主题时调用，不负责生成答案，也不会接收知识库全文：

```bash
QUERY_EXPANSION_ENABLED=1
QUERY_EXPANSION_MAX_TOKENS=180
QUERY_EXPANSION_CACHE_DAYS=30
```

模型只能返回 `canonical_topic`、`synonyms`、`search_queries` 和 `attributes` 四类短 JSON
字段。后端会过滤泛词并校验格式，再交给本地检索做二次排序。扩展结果按规范化问题和模型版本
持久化缓存；超时、非法 JSON 或没有可信结果时直接回退本地检索。该能力不改变答案生成方式。

联网搜索默认关闭，避免普通问题产生额外网页请求和上下文 token。只有在服务端设置
`WEB_SEARCH_ENABLED=1`，并且 API 请求显式传入 `disable_web_search=false` 时，
智能体才会看到 `web_search` 工具；即使启用，也只允许在本地规范库依据不足时尝试一次。

每个问题的 Agent 循环最多执行两轮模型回复：第一轮最多调用一次本地工具，第二轮强制生成
最终答案。工具结果最多回传 8000 字符，模型单次输出上限为 1200 token。结构化记忆默认改用
本地规则提取；需要恢复 LLM 记忆提炼时再显式设置 `MEMORY_LLM_ENABLED=1`。

每次工具调用都会写入现有 `reasoning` / `steps`，前端推理过程展示不需要改动。

## 多地区 / 多城市对比

支持“对比上海和北京的防水规范”“同时查询杭州和南京的容积率规定”这类问题：

```text
用户问题
  -> 提取 regions + topic
  -> compare_regional_standards(regions, topic)
  -> 按地区分别检索本地规范
  -> 分组输出标准、章节、条文、页码
```

- LLM Function Calling 模式下，模型可直接调用 `compare_regional_standards` 并传入 `regions` 列表。
- 未配置 LLM 时，规则解析会自动识别多个地区，并走同一套跨地区对比逻辑。
- 如果某个地区没有收录相关规范，会明确提示“知识库未收录”，不会拿全国规范或其他地区规范顶替。

## Render 部署

仓库根目录已提供 [render.yaml](render.yaml) Blueprint，包含：

- `guibao-api`：FastAPI 后端，PostgreSQL + Redis
- `guibao-web`：Vue 静态前端，自动把 `/api` 指向后端域名
- `guibao-memory-worker`：记忆提炼失败任务重试 worker

确认 `render.yaml` 提交并推送到 Git 仓库后，可通过以下链接在 Render 创建 Blueprint：

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/SophieRabbit/Aspec.git
```

需要在 Dashboard 补填 `LLM_API_BASE` 和 `LLM_API_KEY`。

### 生产环境变量

```bash
# SQL 数据库：生产使用 PostgreSQL，本地不配置时默认 SQLite
MEMORY_DATABASE_URL=postgresql+psycopg://guibao:change-me@127.0.0.1:5432/guibao

# Redis 当前会话缓存；不配置时自动降级为本地内存（仅适合开发）
REDIS_URL=redis://127.0.0.1:6379/0
SESSION_TTL_SECONDS=86400
SESSION_KEEP=20

# 记忆上下文预算
MEMORY_TOKEN_BUDGET=1500
MEMORY_CONTEXT_FACTS=10
MEMORY_MAX_ITEMS_PER_USER=500

# LLM 结构化记忆提炼
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-xxxx
LLM_MODEL=gpt-4o-mini
MEMORY_LLM_ENABLED=0
MEMORY_LLM_TIMEOUT_SECONDS=20
MEMORY_MAX_FACTS_PER_TURN=12
```

本地无 Redis、无 LLM Key 时也能直接运行：Redis 降级为进程内会话缓存，提炼降级为规则抽取。真实上线建议同时启用 PostgreSQL、Redis 和 LLM 提炼。

记忆提炼默认在 Web 进程的后台任务中执行；如果要保证多 worker 或进程重启后任务不丢，可以单独部署一个重试 worker：

```bash
cd backend
python scripts/memory_worker.py --loop 30
```

它会扫描 `memory_jobs` 中 `pending` / `failed` 且未超过重试次数的任务，把原会话消息捞回来继续提炼。

## 导入 PDF 知识库

1. 把可复制文本的规范 PDF 放到 `backend/data/pdfs/`
2. 推荐文件名格式：`GB 55031-2022 民用建筑通用规范.pdf`
3. 推荐目录结构：`国家标准/`、`地方标准/省或市/`、`图集/`，脚本会自动识别地区和类型
4. 运行导入脚本：

```bash
cd backend
python scripts/import_pdfs.py
```

也可以在网页接口文档中单本上传：
`POST /api/knowledge/upload`（文件 + `title` + `standard`）。

后端正在运行时，导入或上传完成后调用 `POST /api/knowledge/reload`
即可让知识库立即生效。

## 大量 PDF 的导入方式

如果资料达到几百 G，不要放到项目目录或通过聊天上传。推荐流程：

1. 在存放 PDF 的服务器或移动硬盘上直接运行导入脚本：

```bash
python scripts/import_pdfs.py --pdf-dir D:\规范资料
```

2. 导入成功后，`backend/data/standards/` 里是可检索的知识库索引，
只需要同步这个目录到部署环境；原 PDF 可删除或归档。
3. 确认检索正常后，再释放原 PDF：

```bash
python scripts/import_pdfs.py --pdf-dir D:\规范资料 --delete-after
```

线上部署时，建议把 `standards/` 放到云服务器磁盘或对象存储挂载目录；
PDF 原文如果要在网页中展示或下载，可存到 OSS/S3 并在索引里记录地址。

## 优先规范库

`backend/data/priority_standards.json` 收录 38 项 GB55 强制性通用规范，全部为优先级 1 级。检索命中这些规范时，
得分会额外加上 `PRIORITY_STANDARD_BOOST`（默认 80）；后续加入的其他优先级标准会按级别自动低一档。

```bash
PRIORITY_STANDARD_BOOST=80
```

查看覆盖情况：

```text
GET /api/knowledge/priority
```

把合法 PDF 放入 `backend/data/priority_pdfs/`，然后导入：

```bash
cd backend
python scripts/import_priority_pdfs.py --pdf-dir data/priority_pdfs
```

脚本会按标准编号/名称自动匹配文件并导入；缺失项会输出清单。规范全文属于版权内容，
系统不自动从第三方网站下载 PDF，请使用已获得授权的规范文本。

GB55 系列全套 PDF 可使用专用导入脚本：

```bash
cd backend
python scripts/import_gb55_pdfs.py --pdf-dir "D:\GB55规范"
```

脚本会自动跳过重复文件、误命名文件和实施指南/宣贯解读等非规范正文，只导入单本规范全文；
所有 `GB55` 编号会自动获得最高优先级。

## 意图识别评测

测试数据：`backend/tests/datasets/intent_router_cases.jsonl`

```bash
cd backend
python scripts/eval_intent.py
```

脚本会输出整体准确率、各类意图召回率和错误分类明细，并生成 `scripts/eval_report.html`。

## 用户反馈

每条助手回答底部提供“有帮助 / 没帮助”反馈。选择“没帮助”时，可以提交问题标签和补充说明。
反馈会关联会话、回答消息、`trace_id`、意图识别结果、知识库版本和回答快照，便于后续分析。

前端同时通过 `/api/analytics/events` 采集匿名产品埋点：

- `page_view`：问答页面浏览，用于统计 PV、UV 和访问会话
- `question_submit` / `answer_complete` / `answer_error`：提问与回答漏斗
- `source_open` / `follow_up_click`：原文查看和追问使用情况
- `feedback_submit`：反馈转化

访客 ID 复用浏览器本地生成的匿名 ID，不写入 Cookie，也不生成浏览器指纹。事件存放在
`analytics_events` 表，看板展示最近 14 天的 PV、UV、会话数、提问数、回答完成率、
原文打开数、反馈转化、流量趋势和最近问题。

同站反馈看板仅供产品经理收藏使用，不展示在普通用户导航中。内部地址为 `/dashboard`，
包含反馈总数、有帮助率、14 天趋势、负反馈原因、问题类型分布和最近 30 条反馈。
看板数据接口也要求登录，不能绕过前端直接匿名读取。

```bash
FEEDBACK_DASHBOARD_USERNAME=zwszff
FEEDBACK_DASHBOARD_PASSWORD=change-me
```

生产环境务必通过环境变量设置独立强密码，并确保站点使用 HTTPS。

配置管理员令牌后，可以导出全部反馈：

```bash
FEEDBACK_ADMIN_TOKEN=your-secret-token
```

```text
GET /api/feedback/export
X-Feedback-Admin-Token: your-secret-token
```

未配置令牌时，导出接口保持关闭。

## 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

接口文档：http://127.0.0.1:8000/docs

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173
