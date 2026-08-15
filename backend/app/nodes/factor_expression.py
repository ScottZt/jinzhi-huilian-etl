"""因子表达式节点 — 用 Qlib 风格 DSL 写因子表达式。

示例表达式：
  MA($close, 20) / STD($close, 20)
  REF($close, 60) / $close - 1
  IF(MA($close, 5) > MA($close, 20) && REF(MA($close, 5), 1) <= REF(MA($close, 20), 1), 1, 0)

输出兼容 factor_write 节点的标准格式：
  code / dt / factor_value
"""
import logging
import traceback
import pandas as pd
from app.core.workflow_engine import BaseNode
from app.core.factor_expr_parser import FactorExprParser, FactorExprError

logger = logging.getLogger(__name__)


class FactorExpressionNode(BaseNode):
    node_type = "factor_expression"
    display_name = "因子表达式"
    category = "因子库"
    params_schema = {
        "expression": {
            "type": "textarea",
            "label": "因子表达式",
            "default": "MA($close, 20) / STD($close, 20)",
        },
        "output_column": {
            "type": "text",
            "label": "输出列名",
            "default": "factor_value",
        },
        "code_column": {
            "type": "text",
            "label": "代码字段（留空=整表计算）",
            "default": "code",
        },
        "date_column": {
            "type": "text",
            "label": "日期字段",
            "default": "dt",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        expr = (params.get("expression") or "").strip()
        if not expr:
            raise ValueError("因子表达式不能为空")

        out_col = params.get("output_column", "factor_value") or "factor_value"
        code_col = (params.get("code_column") or "").strip()
        date_col = params.get("date_column", "dt") or "dt"

        work = df.copy()

        # 按 code 分组计算（每只股票独立时序）
        if code_col and code_col in work.columns:
            groups = []
            errors = []
            for code, sub in work.groupby(code_col):
                try:
                    parser = FactorExprParser(sub.sort_values(date_col))
                    result = parser.parse(expr)
                    sub = sub.copy()
                    sub[out_col] = result.values if hasattr(result, "values") else result
                    groups.append(sub)
                except FactorExprError as e:
                    errors.append(f"[{code}] {e}")
                    logger.warning("factor_expression: 表达式错误 (%s): %s", code, e)
                except Exception as e:
                    errors.append(f"[{code}] {type(e).__name__}: {e}")
                    logger.error("factor_expression: 计算异常 (%s): %s\n%s",
                                 code, e, traceback.format_exc())
            if not groups:
                # 全部失败
                work[out_col] = None
                work["_error"] = "; ".join(errors)
                return work
            work = pd.concat(groups, ignore_index=True)
            if errors:
                work["_error"] = work[code_col].map(
                    {e.split("]")[0][1:]: e for e in errors}
                )
        else:
            # 整表计算
            try:
                parser = FactorExprParser(work.sort_values(date_col) if date_col in work.columns else work)
                result = parser.parse(expr)
                work[out_col] = result.values if hasattr(result, "values") else result
            except FactorExprError as e:
                logger.warning("factor_expression: 表达式错误: %s", e)
                work[out_col] = None
                work["_error"] = str(e)
            except Exception as e:
                logger.error("factor_expression: 计算异常: %s\n%s", e, traceback.format_exc())
                work[out_col] = None
                work["_error"] = f"{type(e).__name__}: {e}"

        return work
