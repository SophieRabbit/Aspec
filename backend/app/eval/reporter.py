from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def generate_report(
    run_id: str,
    dataset_id: str,
    metrics: dict[str, Any],
    results: list[dict[str, Any]],
    regressions: dict[str, float],
    path: Path,
    advice: list[dict[str, Any]] | None = None,
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(_result_row(result) for result in results)
    regression_rows = "".join(
        f"<tr class='regression'><td>{html.escape(metric)}</td><td>{delta:.2%}</td></tr>"
        for metric, delta in regressions.items()
    )
    if not regression_rows:
        regression_rows = "<tr><td colspan='2'>无显著下降</td></tr>"
    advice_html = _advice_html(advice or [])

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>规宝评测报告 {run_id}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#1f2937}}
.card{{border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.metric{{background:#f9fafb;border-radius:8px;padding:12px}}
.bad{{color:#b91c1c}} table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{border:1px solid #e5e7eb;padding:8px;text-align:left}}
th{{background:#f3f4f6}} .regression td{{background:#fef2f2;color:#b91c1c}}
</style></head><body>
<h1>规宝评测报告</h1>
<div class="card"><strong>Run:</strong> {html.escape(run_id)} · <strong>Dataset:</strong> {html.escape(dataset_id)}</div>
<div class="card"><h2>整体指标</h2><div class="metrics">
{_metric_html("检索命中率", metrics.get("retrieval_hit_rate"))}
{_metric_html("关键词覆盖", metrics.get("keyword_coverage"))}
{_metric_html("出处准确率", metrics.get("source_accuracy"))}
{_metric_html("回答完整度", metrics.get("avg_completeness"))}
{_metric_html("延迟 P50(ms)", metrics.get("latency_p50"))}
{_metric_html("延迟 P95(ms)", metrics.get("latency_p95"))}
{_metric_html("Bad Case 数", metrics.get("bad_case_count"))}
</div></div>
<div class="card"><h2>回归对比</h2><table><tr><th>指标</th><th>较上次变化</th></tr>{regression_rows}</table></div>
<div class="card"><h2>自动优化建议</h2>{advice_html}</div>
<div class="card"><h2>逐条结果</h2><table><tr><th>ID</th><th>类别</th><th>问题</th><th>检索</th><th>关键词</th><th>出处</th><th>完整度</th><th>延迟</th><th>Bad</th></tr>{rows}</table></div>
</body></html>"""
    path.write_text(html_text, encoding="utf-8")
    return str(path)


def _metric_html(label: str, value: Any) -> str:
    if value is None:
        display = "-"
    elif isinstance(value, float):
        display = f"{value:.2f}"
    else:
        display = str(value)
    return f"<div class='metric'><div>{html.escape(label)}</div><strong>{html.escape(display)}</strong></div>"


def _result_row(result: dict[str, Any]) -> str:
    metrics = result.get("metrics", {})
    failed = result.get("failed_dimensions", [])
    bad = "是" if result.get("is_bad_case") else "否"
    return (
        "<tr>"
        f"<td>{html.escape(result.get('case_id', ''))}</td>"
        f"<td>{html.escape(result.get('category', ''))}</td>"
        f"<td>{html.escape(result.get('question', ''))[:80]}</td>"
        f"<td>{metrics.get('retrieval', '-')}</td>"
        f"<td>{metrics.get('keyword', '-')}</td>"
        f"<td>{metrics.get('source', '-')}</td>"
        f"<td>{metrics.get('completeness', '-')}</td>"
        f"<td>{metrics.get('latency_ms', '-')}</td>"
        f"<td class='{'bad' if result.get('is_bad_case') else ''}'>{bad} {html.escape(','.join(failed))}</td>"
        "</tr>"
    )


def _advice_html(advice: list[dict[str, Any]]) -> str:
    if not advice:
        return "<p>本次无 Bad Case，无需优化建议。</p>"
    blocks: list[str] = []
    for item in advice:
        causes = "".join(f"<li>{html.escape(cause)}</li>" for cause in item.get("root_causes", []))
        suggestions = "".join(
            f"<li>{html.escape(suggestion)}</li>" for suggestion in item.get("suggestions", [])
        )
        blocks.append(
            "<div class='card'>"
            f"<h3>{html.escape(item.get('label', item.get('dimension', '')))}（{item.get('count', 0)} 条）</h3>"
            "<h4>根因分析</h4><ul>" + causes + "</ul>"
            "<h4>优化建议</h4><ul>" + suggestions + "</ul>"
            "</div>"
        )
    return "".join(blocks)
