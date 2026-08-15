from __future__ import annotations

import sys

from app.eval.service import run_evaluation


def main() -> int:
    result = run_evaluation("qa_test_suite")
    regressions = result.get("regressions", {})
    print(f"run_id={result['run_id']}")
    print(f"metrics={result['metrics']}")
    if regressions:
        print("存在超过 5% 的指标回退：", regressions)
        return 1
    print("回归检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
