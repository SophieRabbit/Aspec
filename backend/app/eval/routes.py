from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .service import run_evaluation
from .store import EvalStore

router = APIRouter(prefix="/eval", tags=["eval"])
store = EvalStore()


class EvalRunRequest(BaseModel):
    dataset_id: str = "qa_test_suite"
    limit: int | None = Field(default=None, ge=1)
    thresholds: dict[str, float] | None = None
    include_user_feedback: bool = True


@router.post("/run")
def eval_run(request: EvalRunRequest) -> dict:
    return run_evaluation(
        dataset_id=request.dataset_id,
        limit=request.limit,
        thresholds=request.thresholds,
        include_user_feedback=request.include_user_feedback,
    )


@router.get("/runs")
def eval_runs() -> list[dict]:
    return store.list_runs()


@router.get("/runs/{run_id}")
def eval_run_detail(run_id: str) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="评测运行不存在")
    for key in ("metrics_json", "regressions_json", "advice_json"):
        if run.get(key):
            run[key.replace("_json", "")] = json.loads(run[key])
    return {**run, "results": store.get_results(run_id)}


@router.get("/runs/{run_id}/report.html", response_class=HTMLResponse)
def eval_report(run_id: str) -> HTMLResponse:
    run = store.get_run(run_id)
    if not run or not run.get("report_path"):
        raise HTTPException(status_code=404, detail="评测报告不存在")
    return HTMLResponse(open(run["report_path"], encoding="utf-8").read())


@router.get("/bad-cases")
def eval_bad_cases() -> list[dict]:
    return store.list_bad_cases()
