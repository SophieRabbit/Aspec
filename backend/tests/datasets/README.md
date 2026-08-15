# 规宝问答评测数据集

数据格式：JSONL，每条记录字段：

- `id`：唯一编号
- `category`：`规范检索` / `地区差异` / `材质对比` / `边界极端`
- `question`：评测输入问题
- `expected_source`：期望命中的规范编号或名称数组，可为空
- `expected_keywords`：期望答案中出现的关键词数组
- `expected_pages`：期望页码数组，可为空
- `notes`：评测说明

说明：当前项目使用本地 JSON 知识库（`backend/data/standards/`），
数据基于现有规范条文反向生成；后续接入 ChromaDB 后可复用同一套测试集。
