"""
脚本执行接口 — 合规设计：提供脚本沙箱执行环境，用于运行大模型生成的 Python 脚本。
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Callable
import sys
import traceback

from etl_tool_sdk.license import LicenseManager
from etl_tool_sdk.config import SDKConfig
from app.core.secure_exec import make_sandbox_globals, safe_exec

logger = logging.getLogger(__name__)


class ScriptExecutor:
    """
    脚本执行器 — 提供安全沙箱环境，执行大模型生成或用户自定义的 Python 脚本。

    合规说明：仅提供脚本执行环境，不存储、不传输任何第三方数据源信息。
    用户生成的脚本需自行审核合规性，因脚本违规使用产生的法律责任由用户承担。

    使用示例：
        executor = ScriptExecutor()

        # 执行自定义脚本（传入 df）
        result_df, error = executor.execute_script(
            code="def process(df):\\n    df['total'] = df['price'] * df['qty']\\n    return df",
            input_data={"df": my_dataframe},
        )

        # 执行完整脚本（自行导入数据、输出数据）
        output_df, error = executor.execute_full_script(
            code=\"\"\"
            import pandas as pd
            df = pd.read_csv('input.csv')
            df['profit'] = df['revenue'] - df['cost']
            df.to_csv('output.csv', index=False)
            print(f"Processed {len(df)} rows")
            \"\"\",
        )

        # 在工具的脚本节点中执行
        result_df, error = executor.execute_node_script(
            code="def process(df):\\n    return df[df['price'] > 100]",
            input_df=input_dataframe,
        )

        # 带断点续传的批量脚本
        results = executor.execute_with_retry(
            script_func=my_sync_func,
            max_retries=3,
            retry_delay=60,
        )
    """

    def __init__(self):
        self._lm = LicenseManager()

    def execute_node_script(
        self,
        code: str,
        input_df: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[pd.DataFrame, Optional[str]]:
        """
        在工具脚本节点环境中执行脚本。

        环境提供：
            pd, np, df（输入 DataFrame）
            context（用户上下文字典）
            print（输出到日志）

        Args:
            code: Python 代码，需定义 process(df) 函数
            input_df: 输入 DataFrame
            context: 额外上下文
        Returns:
            (result_df, error_message)
        """
        if not code:
            return input_df, None

        safe_globals = make_sandbox_globals()
        local_ns = {
            "df": input_df.copy(),
            "context": context or {},
        }

        ok, err = safe_exec(code, safe_globals, local_ns, label="node_script")
        if not ok:
            return input_df, err

        func = local_ns.get("process")
        if callable(func):
            result = func(local_ns["df"])
        elif isinstance(local_ns.get("df"), pd.DataFrame):
            result = local_ns["df"]
        else:
            result = input_df
        if isinstance(result, pd.DataFrame):
            return result, None
        return input_df, None

    def execute_full_script(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        执行完整脚本（自行管理 I/O）。

        合规说明：脚本由用户自行编写或由大模型生成，工具仅提供执行环境。
        用户需自行审核脚本合规性。

        Args:
            code: 完整 Python 脚本
            context: 上下文变量
            timeout: 执行超时（秒）
        Returns:
            (output_df, error_message)
            - 若脚本返回 DataFrame，作为 output_df
            - 若脚本自行写文件，返回 (None, None)
            - 若出错，返回 (None, error_message)
        """
        timeout = timeout or SDKConfig.SANDBOX_TIMEOUT_SECONDS

        safe_globals = make_sandbox_globals()
        local_ns = {"context": context or {}}

        ok, err = safe_exec(code, safe_globals, local_ns, label="full_script")
        if not ok:
            return None, err

        result = local_ns.get("result", local_ns.get("df"))
        if isinstance(result, pd.DataFrame):
            return result, None
        return None, None

    def execute_with_retry(
        self,
        script_func: Callable,
        max_retries: int = 3,
        retry_delay: int = 60,
        backoff: float = 2.0,
    ) -> tuple[Any, Optional[str]]:
        """
        带重试的执行包装器。

        Args:
            script_func: 要执行的函数
            max_retries: 最大重试次数
            retry_delay: 初始重试间隔（秒）
            backoff: 退避系数
        Returns:
            (result, error_message)
        """
        self._lm.check_feature_or_raise("auto_retry")

        import time

        last_error = None
        delay = retry_delay

        for attempt in range(max_retries + 1):
            try:
                result = script_func()
                return result, None
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff
                else:
                    break

        return None, last_error

    def execute_script(
        self,
        code: str,
        input_data: Dict[str, Any],
    ) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        通用脚本执行入口（兼容旧接口）。

        Args:
            code: Python 代码
            input_data: {变量名: 值} 的映射
        Returns:
            (result_df, error_message)
        """
        if "df" in input_data and isinstance(input_data["df"], pd.DataFrame):
            return self.execute_node_script(code, input_data["df"])
        return self.execute_full_script(code, input_data)

    # ---- 沙箱安全工具 ----

    @staticmethod
    def create_safe_globals(
        allow_modules: Optional[list] = None,
    ) -> dict:
        """
        创建安全的全局命名空间。

        Args:
            allow_modules: 允许导入的额外模块（如 ["requests", "bs4"]）
        """
        safe_globals = {
            "pd": pd,
            "np": np,
            "datetime": __import__('datetime').datetime,
            "timedelta": __import__('datetime').timedelta,
            "json": __import__('json'),
            "hashlib": __import__('hashlib'),
            "re": __import__('re'),
            "math": __import__('math'),
            "__builtins__": {
                "len": len,
                "range": range,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "min": min,
                "max": max,
                "sum": sum,
                "abs": abs,
                "round": round,
                "sorted": sorted,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "any": any,
                "all": all,
                "print": print,
            },
        }

        if allow_modules:
            for mod_name in allow_modules:
                try:
                    safe_globals[mod_name] = __import__(mod_name)
                except Exception:
                    pass

        return safe_globals

    def execute_with_timeout(
        self,
        code: str,
        input_data: Dict[str, Any],
        timeout_seconds: int = 300,
    ) -> tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        带超时的脚本执行（使用安全沙箱）。

        注意：Windows 下 subprocess 级别的超时需要多进程支持，
        此方法在超时时会抛出 TimeoutError。
        """
        import signal

        class TimeoutError(Exception):
            pass

        def timeout_handler(signum, frame):
            raise TimeoutError("Script execution timed out")

        local_ns = dict(input_data)
        safe_globals = make_sandbox_globals()

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)

        try:
            ok, err = safe_exec(code, safe_globals, local_ns, label="timeout_script")
            signal.alarm(0)
            if not ok:
                return None, err
            result = local_ns.get("result", local_ns.get("df"))
            if isinstance(result, pd.DataFrame):
                return result, None
            return None, None
        except TimeoutError as e:
            return None, "执行超时"
        except Exception as e:
            signal.alarm(0)
            return None, f"{type(e).__name__}: {e}"
        finally:
            signal.signal(signal.SIGALRM, old_handler)
