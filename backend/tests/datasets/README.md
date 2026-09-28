# 意图识别评测数据集

`intent_router_cases.jsonl` 用于评测 `IntentRouter`，数据格式：

- `id`：唯一编号
- `intent`：期望意图标识
- `question`：用户输入
- `note`：评测说明

运行方式：

```bash
cd backend
python scripts/eval_intent.py
```
