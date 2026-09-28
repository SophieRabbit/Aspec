from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.intent_router import (  # noqa: E402
    INTENT_COLLOQUIAL,
    INTENT_COMPARISON,
    INTENT_LABELS,
    INTENT_MATERIAL,
    INTENT_NAME,
    INTENT_NUMBER,
    INTENT_NUMERIC,
    INTENT_SCENARIO,
    INTENT_TERM,
    INTENT_VERSION,
    IntentRouter,
)


INTENTS = (
    INTENT_NUMBER,
    INTENT_NAME,
    INTENT_TERM,
    INTENT_NUMERIC,
    INTENT_SCENARIO,
    INTENT_COMPARISON,
    INTENT_MATERIAL,
    INTENT_VERSION,
    INTENT_COLLOQUIAL,
)

DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "datasets" / "intent_router_cases.jsonl"
)


def load_cases(path: Path) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        cases.append((str(item["question"]), str(item["intent"])))
    return cases


def escape(text: str) -> str:
    return html.escape(str(text))


def render_report(
    output: Path,
    *,
    total: int,
    correct: int,
    expected_counts: Counter[str],
    correct_counts: Counter[str],
    errors: list[tuple[str, str, str, float]],
    confusion: dict[tuple[str, str], int],
) -> None:
    accuracy = correct / total if total else 0.0
    rows = []
    for intent in INTENTS:
        expected = expected_counts.get(intent, 0)
        hit = correct_counts.get(intent, 0)
        recall = hit / expected if expected else 0.0
        rows.append(
            f"""
            <tr>
              <td>{escape(INTENT_LABELS.get(intent, intent))}</td>
              <td>{escape(intent)}</td>
              <td>{expected}</td>
              <td>{hit}</td>
              <td>{recall:.1%}</td>
            </tr>
            """
        )

    error_rows = []
    for query, expected, actual, confidence in errors:
        error_rows.append(
            f"""
            <tr>
              <td>{escape(query)}</td>
              <td>{escape(INTENT_LABELS.get(expected, expected))}</td>
              <td>{escape(INTENT_LABELS.get(actual, actual))}</td>
              <td>{confidence:.3f}</td>
            </tr>
            """
        )

    confusion_rows = []
    for (expected, actual), count in sorted(confusion.items()):
        if expected == actual:
            continue
        confusion_rows.append(
            f"""
            <tr>
              <td>{escape(INTENT_LABELS.get(expected, expected))}</td>
              <td>{escape(INTENT_LABELS.get(actual, actual))}</td>
              <td>{count}</td>
            </tr>
            """
        )

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>规宝意图识别评测报告</title>
  <style>
    body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2937; }}
    h1 {{ font-size: 22px; }}
    .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 22px; background: #f9fafb; }}
    .card b {{ font-size: 28px; color: #0f766e; }}
    table {{ border-collapse: collapse; width: 100%; margin: 18px 0; background: #fff; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .ok {{ color: #047857; }}
    .bad {{ color: #b91c1c; }}
  </style>
</head>
<body>
  <h1>规宝意图识别评测报告</h1>
  <div class="summary">
    <div class="card"><div>总用例</div><b>{total}</b></div>
    <div class="card"><div>正确</div><b>{correct}</b></div>
    <div class="card"><div>整体准确率</div><b>{accuracy:.1%}</b></div>
  </div>
  <h2>各类意图召回率</h2>
  <table>
    <thead><tr><th>意图</th><th>标识</th><th>用例数</th><th>正确数</th><th>召回率</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>错误分类明细</h2>
  <table>
    <thead><tr><th>用户问题</th><th>期望意图</th><th>识别结果</th><th>置信度</th></tr></thead>
    <tbody>{''.join(error_rows) if error_rows else '<tr><td colspan="4">无错误</td></tr>'}</tbody>
  </table>
  <h2>混淆明细</h2>
  <table>
    <thead><tr><th>期望意图</th><th>被识别为</th><th>数量</th></tr></thead>
    <tbody>{''.join(confusion_rows) if confusion_rows else '<tr><td colspan="3">无混淆</td></tr>'}</tbody>
  </table>
</body>
</html>
"""
    output.write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="评测规宝 IntentRouter 意图识别效果")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "eval_report.html",
        help="HTML 报告输出路径",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="意图测试用例 JSONL 路径",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="是否启用 LLM 二阶段分类（默认仅规则+兜底，保证结果可复现）",
    )
    args = parser.parse_args()

    router = IntentRouter()
    cases = load_cases(args.cases)
    expected_counts: Counter[str] = Counter()
    correct_counts: Counter[str] = Counter()
    actual_counts: Counter[str] = Counter()
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    errors: list[tuple[str, str, str, float]] = []

    for query, expected in cases:
        result = router.route(query, use_llm=args.use_llm)
        actual = result.intent
        expected_counts[expected] += 1
        actual_counts[actual] += 1
        confusion[(expected, actual)] += 1
        if actual == expected:
            correct_counts[expected] += 1
        else:
            errors.append((query, expected, actual, result.confidence))

    total = len(cases)
    correct = sum(correct_counts.values())
    accuracy = correct / total if total else 0.0

    print(f"总用例：{total}")
    print(f"正确：{correct}")
    print(f"整体准确率：{accuracy:.2%}")
    print()
    print("各类意图召回率：")
    for intent in INTENTS:
        expected = expected_counts.get(intent, 0)
        hit = correct_counts.get(intent, 0)
        recall = hit / expected if expected else 0.0
        print(f"  {INTENT_LABELS.get(intent, intent):<8} {hit}/{expected} = {recall:.2%}")
    print()
    print("错误分类明细：")
    if not errors:
        print("  无错误")
    else:
        for query, expected, actual, confidence in errors:
            print(
                f"  {query} | 期望：{INTENT_LABELS.get(expected, expected)} "
                f"| 识别：{INTENT_LABELS.get(actual, actual)} | 置信度：{confidence:.3f}"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    render_report(
        args.output,
        total=total,
        correct=correct,
        expected_counts=expected_counts,
        correct_counts=correct_counts,
        errors=errors,
        confusion=confusion,
    )
    print()
    print(f"HTML 报告已生成：{args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
