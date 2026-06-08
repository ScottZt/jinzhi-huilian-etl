"""
Safe execution sandbox — prevents exec/eval sandbox escapes.

Attack vectors mitigated:
  - Object introspection escape: obj.__class__.__bases__[0].__subclasses__()
  - Function introspection escape: func.__globals__['__builtins__']
  - Dynamic attribute access: getattr(pd, '__class__')
  - Import / open / compile / eval / exec injection

Design:
  1. AST-level validation rejects code with dangerous constructs (import, exec, eval, open, compile).
  2. An ObjectProxy blocks all dunder attribute access on wrapped sandbox objects.
  3. Code size is limited (default 64 KB).
  4. All executions are logged.
"""
import ast
import logging
import textwrap
import traceback
from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ---- Config ----
MAX_CODE_BYTES = 64 * 1024  # 64 KB limit

# Forbidden AST node patterns
_FORBIDDEN_BUILTINS = frozenset({
    "open", "compile", "exec", "eval", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "input", "breakpoint",
})

# Forbidden attribute names that enable sandbox escape
_FORBIDDEN_ATTRS = frozenset({
    "__class__", "__bases__", "__mro__", "__subclasses__", "__globals__",
    "__builtins__", "__dict__", "__code__", "__qualname__", "__closure__",
    "__func__", "__self__", "__wrapped__", "__getattribute__",
    "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__",
})


# ---- AST validation ----

class _DangerVisitor(ast.NodeVisitor):
    """Reject code that imports, calls forbidden builtins, or uses dunder attr access."""

    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import):
        self.violations.append(f"import is not allowed in sandbox (line {node.lineno})")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.violations.append(f"'from ... import' is not allowed in sandbox (line {node.lineno})")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Check if calling a forbidden builtin name
        if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_BUILTINS:
            self.violations.append(
                f"call to '{node.func.id}' is blocked (line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in _FORBIDDEN_ATTRS:
            self.violations.append(
                f"access to '{node.attr}' is blocked (line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in _FORBIDDEN_BUILTINS:
            self.violations.append(
                f"reference to '{node.id}' is blocked (line {node.lineno})"
            )
        self.generic_visit(node)


def validate_code_ast(code: str) -> Tuple[bool, str]:
    """Return (is_safe, error_message)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    visitor = _DangerVisitor()
    visitor.visit(tree)
    if visitor.violations:
        return False, "; ".join(visitor.violations)
    return True, ""


# ---- Object proxy for dunder blocking ----

class _SafeProxy:
    """Wraps an object and blocks access to dangerous dunder attributes."""

    __slots__ = ("_obj", "_allowed_attrs")

    def __init__(self, obj: Any, allowed_attrs: Optional[set] = None):
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_allowed_attrs", allowed_attrs or set())

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_ATTRS or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(f"Access to '{name}' is blocked in sandbox")
        val = getattr(self._obj, name)
        # If the result is callable, wrap it too (prevent escape via returned functions)
        if callable(val):
            return _SafeProxy(val)
        return val

    def __setattr__(self, name: str, value):
        if name in _FORBIDDEN_ATTRS or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(f"Cannot set '{name}' in sandbox")
        return setattr(self._obj, name, value)

    def __repr__(self):
        return repr(self._obj)

    def __str__(self):
        return str(self._obj)

    # Allow iteration, containment, etc.
    def __iter__(self):
        return iter(self._obj)

    def __contains__(self, item):
        return item in self._obj

    def __len__(self):
        return len(self._obj)

    def __getitem__(self, key):
        return self._obj[key]

    def __setitem__(self, key, value):
        self._obj[key] = value

    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)


def _wrap_globals(globals_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap all non-builtin values in the globals dict with _SafeProxy."""
    wrapped = {}
    for k, v in globals_dict.items():
        if k == "__builtins__":
            wrapped[k] = v  # keep as-is (should be empty {})
        elif callable(v) or hasattr(v, "__class__"):
            wrapped[k] = _SafeProxy(v)
        else:
            wrapped[k] = v
    return wrapped


# ---- Main execution helpers ----

def safe_exec(
    code: str,
    safe_globals: Optional[Dict[str, Any]] = None,
    local_ns: Optional[Dict[str, Any]] = None,
    *,
    label: str = "sandbox",
) -> Tuple[bool, Optional[str]]:
    """
    Execute code in a restricted sandbox with AST validation and dunder blocking.

    Args:
        code: Python source code to execute.
        safe_globals: Global namespace (should already contain sandbox-provided objects).
        local_ns: Local namespace (e.g., {"df": dataframe}).
        label: Logging label for audit.

    Returns:
        (success, error_message)
    """
    # 1. Size check
    if len(code.encode()) > MAX_CODE_BYTES:
        return False, f"Code exceeds maximum size of {MAX_CODE_BYTES // 1024} KB"

    # 2. AST validation
    ok, err = validate_code_ast(code)
    if not ok:
        return False, f"Code rejected: {err}"

    # 3. Prepare namespace
    if safe_globals is None:
        safe_globals = {"__builtins__": {}}
    safe_globals = _wrap_globals(safe_globals)

    if local_ns is None:
        local_ns = {}

    # 4. Execute
    try:
        exec(code, safe_globals, local_ns)
        logger.info("[sandbox:%s] Code executed successfully", label)
        return True, None
    except Exception as e:
        tb = traceback.format_exc()
        logger.warning("[sandbox:%s] Execution error: %s\n%s", label, e, tb)
        return False, f"{type(e).__name__}: {e}\n{tb}"


def safe_eval(
    expr: str,
    safe_globals: Optional[Dict[str, Any]] = None,
    local_ns: Optional[Dict[str, Any]] = None,
    *,
    label: str = "sandbox",
) -> Tuple[bool, Any]:
    """
    Evaluate expression in a restricted sandbox.

    Returns:
        (success, result_or_error)
    """
    if len(expr.encode()) > 4096:
        return False, "Expression exceeds size limit"

    ok, err = validate_code_ast(expr)
    if not ok:
        return False, f"Expression rejected: {err}"

    if safe_globals is None:
        safe_globals = {"__builtins__": {}}
    safe_globals = _wrap_globals(safe_globals)

    if local_ns is None:
        local_ns = {}

    try:
        result = eval(expr, safe_globals, local_ns)
        return True, result
    except Exception as e:
        logger.warning("[sandbox:%s] Eval error: %s", label, e)
        return False, f"{type(e).__name__}: {e}"


# ---- Pre-built sandbox globals ----

def make_sandbox_globals(
    *,
    allow_numpy: bool = True,
    allow_datetime: bool = True,
    allow_json: bool = False,
    allow_re: bool = False,
    extra_builtins: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a sandbox globals dict with wrapped safe objects.

    The returned dict already has __builtins__ = {}.
    """
    sandbox: Dict[str, Any] = {
        "__builtins__": {},
        "pd": pd,
    }

    if allow_numpy:
        sandbox["np"] = np
        sandbox["np_where"] = np.where
        sandbox["np_select"] = np.select

    if allow_datetime:
        import datetime as _dt
        sandbox["datetime"] = _dt.datetime
        sandbox["timedelta"] = _dt.timedelta

    if allow_json:
        import json
        sandbox["json"] = json

    if allow_re:
        import re
        sandbox["re"] = re

    if extra_builtins:
        sandbox.update(extra_builtins)

    return sandbox
