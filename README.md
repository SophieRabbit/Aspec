# 规宝 v1.0

工程规范智能问答平台（B端），Vue 3 + Vite 前端，Python FastAPI 后端。

## 当前能力

- 自然语言提问，从预构建知识库检索规范条文
- 返回答案、出处（标准/章节/条文/页码）、延伸问题
- Agent 自主规划：条文检索、数值计算、规范对比
- 多轮记忆：短期对话窗口 + 长期事实抽取 + Token 预算控制
- 响应式界面：PC 左侧会话列表 + 右侧聊天，移动端全屏聊天
- 支持上传 PDF 生成可检索的知识文档

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
