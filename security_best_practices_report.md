# 规宝安全最佳实践审查报告

审查范围：FastAPI 后端 + Vue 3 前端，涉及登录前匿名用户、会话记忆、LLM Function Calling、PDF 知识库上传、联网搜索和评测接口。

## 执行摘要

当前项目没有发现已提交的真实密钥或 SQL 注入等可直接利用的 Critical 问题，但**上线前必须先解决用户身份可信边界**。当前所有接口都信任客户端传入的 `X-User-Id` 或 `user_id`，任意用户都可以伪造其他用户 ID，从而读取、删除他人会话和记忆。其次，聊天和上传接口缺少认证、限流和上传大小限制，存在成本滥用和拒绝服务风险。

## High 风险

### SEC-001：用户身份完全由客户端控制，可越权访问其他用户数据

- 严重性：High
- 位置：
  - [backend/app/api/routes.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/api/routes.py:31)
  - [frontend/src/api.js](C:/Users/zhaof/Documents/trae_projects/aspec/frontend/src/api.js:1)
- 证据：

```python
def _resolve_user_id(header_user_id: str | None, payload_user_id: str | None = None) -> str:
    raw = header_user_id or payload_user_id or "default"
    cleaned = re.sub(r"[^0-9a-zA-Z_.:-]", "", raw).strip()[:128]
    return cleaned or "default"
```

```js
localStorage.setItem('guibao_user_id', userId)
'X-User-Id': ensureUserId(),
```

- 影响：攻击者可以任意设置 `X-User-Id: victim-id` 来读取、删除受害者的会话、消息和长期记忆，属于跨用户数据泄露。
- 修复：后端必须从服务端身份源（登录后的 JWT、会话 Cookie 或网关注入的受信 User ID）获取用户身份，不再信任客户端 Header 或查询参数。
- 缓解：在正式鉴权接入前，至少不要接受任意查询参数 `user_id`；匿名模式应由后端签发不透明会话 ID。

### SEC-002：聊天、上传和反馈接口缺少认证与限流

- 严重性：High
- 位置：
  - [backend/app/api/routes.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/api/routes.py:218)
  - [backend/app/api/routes.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/api/routes.py:325)
- 证据：`chat()` 和 `feedback_bad_case()` 都没有 `Depends()` / `Security()`，也没有任何节流逻辑。
- 影响：攻击者可以无限制调用 LLM Function Calling，产生高额模型费用；也可以批量写入坏例反馈，污染评测数据。
- 修复：为受保护接口统一添加认证依赖，并在应用层或网关层按用户/IP 限流；LLM 接口应设置更严格的配额和预算告警。

## Medium 风险

### SEC-003：PDF 上传只校验扩展名，无大小、内容和解析限制

- 严重性：Medium
- 位置：[backend/app/api/routes.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/api/routes.py:114)
- 证据：

```python
suffix = Path(file.filename or "").suffix.lower()
if suffix != ".pdf":
    raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
temp_path = DATA_DIR / f"upload-{uuid.uuid4().hex}.pdf"
```

- 影响：超大或恶意构造的 PDF 可以消耗磁盘、CPU 和内存，造成拒绝服务；只改扩展名的非 PDF 文件也可能进入解析流程。
- 修复：限制上传大小（例如 50MB），用 PDF magic bytes 和 `pypdf` 可打开性校验内容，解析加入超时和页数/文本长度上限；大型文件应改为异步导入。

### SEC-004：生产环境默认暴露 OpenAPI 文档

- 严重性：Medium
- 位置：[backend/app/main.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/main.py:10)
- 证据：`FastAPI(...)` 未设置 `docs_url=None`、`redoc_url=None`、`openapi_url=None`，也没有环境开关。
- 影响：公开部署后 `/docs`、`/redoc`、`/openapi.json` 会暴露完整接口结构，放大攻击面。
- 修复：增加 `ENVIRONMENT=production` 配置，生产环境禁用 docs，或放到带鉴权的内部路由。

### SEC-005：缺少 TrustedHostMiddleware

- 严重性：Medium
- 位置：[backend/app/main.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/main.py:16)
- 证据：应用只注册了 CORSMiddleware，没有 `TrustedHostMiddleware`。
- 影响：在反代/公网环境下，攻击者可能通过伪造 Host 头影响绝对 URL 生成、缓存和日志，并为其他攻击提供基础。
- 修复：配置 `TrustedHostMiddleware(allowed_hosts=[...])`，生产环境只允许业务域名。

### SEC-006：前端缺少 CSP 和安全响应头配置

- 严重性：Medium
- 位置：[frontend/index.html](C:/Users/zhaof/Documents/trae_projects/aspec/frontend/index.html:1)
- 证据：`index.html` 没有任何 CSP meta；仓库中也看不到静态托管层的 `Content-Security-Policy`、`X-Frame-Options`、`X-Content-Type-Options` 配置。
- 影响：聊天内容通过 `v-html` 渲染（虽然有先转义再生成标签的逻辑），缺少 CSP 会让 XSS 的防护深度明显不足。
- 修复：在 Nginx/CDN/Render 静态站点配置严格 CSP、`frame-ancestors`、`nosniff`；同时把富文本渲染集中到经过审查的 sanitizer。

## Low 风险

### SEC-007：计算工具使用 `eval` 执行经过 AST 白名单校验的表达式

- 严重性：Low
- 位置：[backend/app/agent/tools.py](C:/Users/zhaof/Documents/trae_projects/aspec/backend/app/agent/tools.py:43)
- 证据：

```python
return eval(compile(tree, "<expression>", "eval"), {"__builtins__": {}}, {})
```

- 说明：当前白名单只允许常量、四则运算和一元运算，风险较低，但 `eval` 属于高风险模式，后续新增运算符时容易扩大攻击面。
- 修复：继续收紧 AST 节点白名单，增加自动化测试覆盖恶意表达式；如果未来要支持更多函数，优先使用安全求值库或解释器。

### SEC-008：Python 依赖使用宽泛版本范围，依赖审计不可用

- 严重性：Low
- 位置：[backend/requirements.txt](C:/Users/zhaof/Documents/trae_projects/aspec/backend/requirements.txt:1)
- 证据：`fastapi>=0.115.0`、`pydantic>=2.10.0` 等均为最低版本约束，没有锁定。
- 影响：不同环境可能安装不同版本，产生供应链和补丁漂移风险。
- 修复：为生产锁定精确版本并提交 lock 文件；将 `pip-audit` 和官方 npm registry 的 `npm audit` 接入 CI。本次审查中本机 npm registry 镜像未实现 audit 接口，因此前端依赖审计未能完成。

## 未在代码中可见、需上线前确认的项目

- TLS/HTTPS 终止和强制跳转：应由云负载均衡、CDN 或反向代理提供。
- 网关层限流、WAF、请求体大小限制：建议在 Nginx/API 网关/云厂商处配置。
- 数据库和 Redis 的网络隔离、备份、加密：应在云环境安全组和数据库配置中确认。
- 正式登录体系：当前匿名用户机制不能作为生产鉴权方案。
