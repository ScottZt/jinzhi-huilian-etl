"""因子表达式 DSL 解析器 — 把用户表达式字符串安全求值为 pd.Series。

DSL 语法：
  - 变量：$close, $open, $high, $low, $vol, $volume, $amount（或直接写列名）
  - 时序函数：MA(s, n), EMA(s, n), STD(s, n), REF(s, n), RSI(s, n), ATR(n), ...
  - 数学函数：ABS, LOG, SQRT, POW, SIGN, CEIL, FLOOR, ROUND
  - 运算符：+ - * / ^（幂） % > < >= <= == != && || !
  - 括号任意嵌套，支持 IF(cond, a, b) 三元条件

实现：
  1. 预处理：$x → __col_x__, && → and, || → or, ^ → **
  2. ast.parse(expr, mode='eval') 转 AST
  3. 白名单校验 AST 节点
  4. 递归求值 _eval(node, env)
"""
import ast
import re
from typing import Any
import numpy as np
import pandas as pd

from app.core.factor_expr_ops import OPS_REGISTRY


# ============================================================
# AST 白名单
# ============================================================

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Call, ast.Name, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.IfExp,
    ast.Load,  # 变量加载上下文（Name/Constant 等需要）
    # Python 3.8+ 的 ast.Constant 同时覆盖 Num/Str 等，为兼容旧版保留：
    getattr(ast, "Num", ast.Constant),
    getattr(ast, "NameConstant", ast.Constant),
)

# 内置常量
_CONSTANTS = {
    "nan": np.nan,
    "NaN": np.nan,
    "NAN": np.nan,
    "inf": np.inf,
    "Inf": np.inf,
    "pi": np.pi,
    "e": np.e,
    "true": True,
    "True": True,
    "false": False,
    "False": False,
}


class FactorExprError(Exception):
    """DSL 解析/求值错误。"""


# ============================================================
# 预处理
# ============================================================

def _preprocess(expr: str) -> str:
    """把用户友好的语法转成合法 Python 表达式。"""
    if not expr or not expr.strip():
        raise FactorExprError("表达式为空")

    # 去掉注释（# 开头到行尾）
    expr = re.sub(r"#[^\n]*", "", expr).strip()
    if not expr:
        raise FactorExprError("表达式为空（仅含注释）")

    # $close → __col_close__（合法 Python 变量名）
    def _replace_var(m):
        return "__col_" + m.group(1) + "__"
    expr = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", _replace_var, expr)

    # 逻辑运算符（注意顺序：先处理 && ||，再处理 !，避免误伤 !=）
    expr = expr.replace("&&", " and ")
    expr = expr.replace("||", " or ")
    # ! 单独出现（后面不是 =）→ not
    expr = re.sub(r"!(?!=)", " not ", expr)

    # ^ 作为幂运算（Python 里 ^ 是异或，我们要 **）
    # 但小心字符串里的 ^，以及 != 这种
    expr = expr.replace("^", "**")

    return expr


def _extract_columns(expr: str) -> set:
    """从原始表达式中提取 $xxx 字段名（预处理前）。"""
    return set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", expr))


# ============================================================
# 解析器
# ============================================================

class FactorExprParser:
    """因子表达式解析器。

    用法：
        parser = FactorExprParser(df)
        result = parser.parse("MA($close, 20) / STD($close, 20)")
        # result: pd.Series
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self._columns = set(df.columns)

    def parse(self, expr: str) -> pd.Series:
        """解析表达式并返回结果 Series。"""
        processed = _preprocess(expr)
        try:
            tree = ast.parse(processed, mode="eval")
        except SyntaxError as e:
            raise FactorExprError(f"表达式语法错误: {e.msg} (line {e.lineno})")

        self._validate(tree)
        env = self._build_env()
        result = self._eval(tree.body, env)

        if isinstance(result, pd.Series):
            return result.reindex(self.df.index)
        # 标量 → 广播为 Series
        return pd.Series(result, index=self.df.index)

    # --------------------------------------------------------
    # AST 校验
    # --------------------------------------------------------
    def _validate(self, node):
        """递归校验 AST，拒绝非白名单节点。"""
        if not isinstance(node, _ALLOWED_NODES):
            raise FactorExprError(
                f"不允许的语法: {type(node).__name__}。"
                f"只支持算术、比较、逻辑运算和函数调用。"
            )
        for child in ast.iter_child_nodes(node):
            self._validate(child)

    # --------------------------------------------------------
    # 环境构建
    # --------------------------------------------------------
    def _build_env(self) -> dict:
        """构建求值环境：把 DataFrame 列映射为 __col_xxx__ 变量。"""
        env = {}
        for col in self._columns:
            env[f"__col_{col}__"] = self.df[col].astype(float) if self.df[col].dtype.kind in "biufc" else self.df[col]
        env.update(_CONSTANTS)
        return env

    # --------------------------------------------------------
    # 递归求值
    # --------------------------------------------------------
    def _eval(self, node, env: dict) -> Any:
        if isinstance(node, ast.BinOp):
            left = self._eval(node.left, env)
            right = self._eval(node.right, env)
            return self._apply_binop(node.op, left, right)

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, env)
            return self._apply_unaryop(node.op, operand)

        if isinstance(node, ast.BoolOp):
            values = [self._eval(v, env) for v in node.values]
            if isinstance(node.op, ast.And):
                result = values[0]
                for v in values[1:]:
                    result = result & v
                return result
            else:  # Or
                result = values[0]
                for v in values[1:]:
                    result = result | v
                return result

        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, env)
                left = self._apply_compare(op, left, right)
                if not isinstance(left, (pd.Series, bool, np.bool_)):
                    break
            return left

        if isinstance(node, ast.Call):
            return self._eval_call(node, env)

        if isinstance(node, ast.Name):
            name = node.id
            if name in env:
                return env[name]
            # 也尝试直接映射到 DataFrame 列（允许无 $ 前缀写法）
            if name in self._columns:
                return self.df[name].astype(float) if self.df[name].dtype.kind in "biufc" else self.df[name]
            raise FactorExprError(f"未定义的变量: '{name}'。可用列: {sorted(self._columns)}")

        if isinstance(node, ast.Constant):
            return node.value

        # 兼容 Python 3.7 的 ast.Num / ast.NameConstant
        if hasattr(ast, "Num") and isinstance(node, ast.Num):
            return node.n
        if hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):
            return node.value

        if isinstance(node, ast.IfExp):
            cond = self._eval(node.test, env)
            a = self._eval(node.body, env)
            b = self._eval(node.orelse, env)
            return OPS_REGISTRY["IF"](cond, a, b)

        raise FactorExprError(f"不支持的节点: {type(node).__name__}")

    # --------------------------------------------------------
    # 函数调用
    # --------------------------------------------------------
    def _eval_call(self, node: ast.Call, env: dict) -> Any:
        if not isinstance(node.func, ast.Name):
            raise FactorExprError("只支持直接函数调用，不支持方法/属性调用")
        fname = node.func.id
        if fname not in OPS_REGISTRY:
            raise FactorExprError(
                f"未知函数: '{fname}'。可用: {sorted(OPS_REGISTRY.keys())}"
            )
        op = OPS_REGISTRY[fname]
        args = [self._eval(a, env) for a in node.args]

        # ATR 特殊：第一个参数应是 DataFrame（包含 high/low/close）
        if fname == "ATR":
            return op(self.df, *args)

        # IF 特殊：已在 IfExp 处理，这里也兼容函数式调用
        if fname == "IF":
            if len(args) != 3:
                raise FactorExprError(f"IF 需要 3 个参数，实际 {len(args)} 个")
            return op(*args)

        return op(*args)

    # --------------------------------------------------------
    # 运算符映射
    # --------------------------------------------------------
    @staticmethod
    def _apply_binop(op, left, right):
        if isinstance(op, ast.Add): return _safe(left, right, lambda a, b: a + b)
        if isinstance(op, ast.Sub): return _safe(left, right, lambda a, b: a - b)
        if isinstance(op, ast.Mult): return _safe(left, right, lambda a, b: a * b)
        if isinstance(op, ast.Div): return _safe(left, right, lambda a, b: a / b)
        if isinstance(op, ast.Mod): return _safe(left, right, lambda a, b: a % b)
        if isinstance(op, ast.Pow): return _safe(left, right, lambda a, b: a ** b)
        if isinstance(op, ast.FloorDiv): return _safe(left, right, lambda a, b: a // b)
        raise FactorExprError(f"不支持的二元运算符: {type(op).__name__}")

    @staticmethod
    def _apply_unaryop(op, operand):
        if isinstance(op, ast.UAdd): return +operand
        if isinstance(op, ast.USub): return -operand
        if isinstance(op, ast.Not):
            if isinstance(operand, pd.Series):
                return ~operand.astype(bool)
            return not operand
        if isinstance(op, ast.Invert):
            return ~operand
        raise FactorExprError(f"不支持的一元运算符: {type(op).__name__}")

    @staticmethod
    def _apply_compare(op, left, right):
        if isinstance(op, ast.Eq): return left == right
        if isinstance(op, ast.NotEq): return left != right
        if isinstance(op, ast.Lt): return left < right
        if isinstance(op, ast.LtE): return left <= right
        if isinstance(op, ast.Gt): return left > right
        if isinstance(op, ast.GtE): return left >= right
        raise FactorExprError(f"不支持的比较运算符: {type(op).__name__}")


# ============================================================
# 工具
# ============================================================

def _safe(left, right, fn):
    """执行二元运算，捕获除零等错误。"""
    try:
        return fn(left, right)
    except ZeroDivisionError:
        # 返回带 NaN 的 Series
        if isinstance(left, pd.Series):
            return pd.Series(np.nan, index=left.index)
        if isinstance(right, pd.Series):
            return pd.Series(np.nan, index=right.index)
        return np.nan
    except Exception as e:
        raise FactorExprError(f"运算失败: {e}")
