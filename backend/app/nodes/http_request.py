"""HTTP 请求节点 — 调用外部 API。"""
import logging
import json
import requests
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class HttpRequestNode(BaseNode):
    node_type = "http_request"
    display_name = "HTTP 请求"
    category = "数据集成"
    params_schema = {
        "method": {"type": "select", "label": "请求方法", "options": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
        "url": {"type": "text", "label": "请求 URL", "default": "",
                "placeholder": "https://api.example.com/data"},
        "headers": {"type": "textarea", "label": "请求头 (JSON)", "default": "{}",
                    "placeholder": '{"Content-Type": "application/json", "Authorization": "Bearer {{token}}"}'},
        "body_type": {"type": "select", "label": "请求体类型", "options": ["none", "json", "form", "text"], "default": "none"},
        "body": {"type": "textarea", "label": "请求体", "default": "",
                 "placeholder": "JSON 格式或其他格式的请求内容"},
        "timeout": {"type": "number", "label": "超时时间(秒)", "default": 30},
        "auth_type": {"type": "select", "label": "认证类型", "options": ["none", "bearer", "basic"], "default": "none"},
        "auth_token": {"type": "text", "label": "认证令牌", "default": "",
                       "placeholder": "Bearer Token 或用户名:密码"},
        "response_type": {"type": "select", "label": "响应类型", "options": ["json", "text", "auto"], "default": "auto"},
        "output_column": {"type": "text", "label": "输出列名", "default": "response",
                          "placeholder": "将响应数据存储到此列"},
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        执行 HTTP 请求并返回响应数据。
        """
        method = params.get("method", "GET").upper()
        url = params.get("url", "").strip()
        timeout = int(params.get("timeout", 30))
        response_type = params.get("response_type", "auto")
        output_column = params.get("output_column", "response")

        if not url:
            logger.error("HttpRequestNode: URL 不能为空")
            return self._create_error_df(df, "URL 不能为空")

        # 解析 Headers
        headers = self._parse_headers(params.get("headers", "{}"))

        # 添加认证
        headers = self._add_auth(headers, params)

        # 准备请求体
        body = self._prepare_body(params)

        try:
            # 执行请求
            logger.info("HttpRequestNode: %s %s", method, url)
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                timeout=timeout,
                **body
            )

            # 检查响应状态
            response.raise_for_status()

            # 解析响应
            result = self._parse_response(response, response_type)

            # 将结果添加到 DataFrame
            if isinstance(result, dict):
                # JSON 响应，展开为列
                result_df = pd.DataFrame([result])
                return result_df
            elif isinstance(result, list):
                # JSON 数组响应
                result_df = pd.DataFrame(result)
                return result_df
            else:
                # 文本响应，添加到新列
                if df.empty:
                    df = pd.DataFrame({"index": [0]})
                df[output_column] = str(result)
                return df

        except requests.exceptions.Timeout:
            logger.error("HttpRequestNode: 请求超时")
            return self._create_error_df(df, f"请求超时（{timeout}秒）")
        except requests.exceptions.HTTPError as e:
            logger.error("HttpRequestNode: HTTP 错误: %s", e)
            return self._create_error_df(df, f"HTTP 错误: {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error("HttpRequestNode: 请求异常: %s", e)
            return self._create_error_df(df, f"请求异常: {str(e)}")
        except Exception as e:
            logger.error("HttpRequestNode: 未知错误: %s", e)
            return self._create_error_df(df, f"未知错误: {str(e)}")

    def _parse_headers(self, headers_str: str) -> dict:
        """解析 Headers JSON 字符串。"""
        try:
            if isinstance(headers_str, str):
                return json.loads(headers_str) if headers_str.strip() else {}
            return headers_str if isinstance(headers_str, dict) else {}
        except Exception as e:
            logger.warning("HttpRequestNode: Headers 解析失败: %s", e)
            return {}

    def _add_auth(self, headers: dict, params: dict) -> dict:
        """添加认证信息到 Headers。"""
        auth_type = params.get("auth_type", "none")
        auth_token = params.get("auth_token", "").strip()

        if not auth_token or auth_type == "none":
            return headers

        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {auth_token}"
        elif auth_type == "basic":
            import base64
            encoded = base64.b64encode(auth_token.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        return headers

    def _prepare_body(self, params: dict) -> dict:
        """准备请求体。"""
        body_type = params.get("body_type", "none")
        body_str = params.get("body", "").strip()

        if body_type == "none" or not body_str:
            return {}

        if body_type == "json":
            try:
                return {"json": json.loads(body_str)}
            except Exception as e:
                logger.warning("HttpRequestNode: JSON 请求体解析失败: %s", e)
                return {"data": body_str}

        elif body_type == "form":
            try:
                # 尝试解析为 JSON，然后转为 form data
                form_data = json.loads(body_str)
                return {"data": form_data}
            except Exception:
                # 如果是 key=value&key2=value2 格式
                return {"data": body_str}

        elif body_type == "text":
            return {"data": body_str}

        return {}

    def _parse_response(self, response: requests.Response, response_type: str):
        """解析响应数据。"""
        if response_type == "json" or (response_type == "auto" and "application/json" in response.headers.get("Content-Type", "")):
            try:
                return response.json()
            except Exception as e:
                logger.warning("HttpRequestNode: JSON 解析失败: %s", e)
                return response.text
        elif response_type == "text":
            return response.text
        else:
            # auto 模式，尝试 JSON，失败则返回文本
            try:
                return response.json()
            except Exception:
                return response.text

    def _create_error_df(self, df: pd.DataFrame, error_msg: str) -> pd.DataFrame:
        """创建错误 DataFrame。"""
        if df.empty:
            return pd.DataFrame({"error": [error_msg]})
        df["error"] = error_msg
        return df
