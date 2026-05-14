"""一键执行内置预制工作流并输出结果。"""
import json

import pandas as pd

from app.core.workflow_engine import get_workflow_engine
from app.core.workflow_presets import get_workflow_presets
from app.persistence.sqlite_repo import init_db


def main() -> int:
    """执行所有预制工作流，任一失败返回非 0。"""
    # 初始化数据库，确保本地环境完整。
    init_db()

    engine = get_workflow_engine()
    # 注册节点，避免执行期出现未知节点类型。
    engine.register_all()

    summary = []
    for preset in get_workflow_presets():
        df = pd.DataFrame(preset.get("sample_data", []))
        try:
            result_df, timings = engine.execute(preset["workflow_json"], df)
            summary.append(
                {
                    "key": preset["key"],
                    "name": preset["name"],
                    "input_rows": len(df),
                    "output_rows": len(result_df),
                    "output_columns": list(result_df.columns),
                    "timings": timings,
                    "ok": True,
                }
            )
        except Exception as exc:
            summary.append(
                {
                    "key": preset["key"],
                    "name": preset["name"],
                    "input_rows": len(df),
                    "ok": False,
                    "error": str(exc),
                }
            )

    print(json.dumps({"runs": summary}, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
