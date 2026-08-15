"""插件节点注册中心。"""
import os
import json
import importlib
import inspect
from pathlib import Path
from app.core.workflow_engine import BaseNode

_builtin_nodes: list = []           # 内置节点 type 列表
_official_cache: dict | None = None # official.json 缓存 {node_type: meta}


class NodeRegistry:
    _nodes: dict = {}

    @classmethod
    def register(cls, node_class: type):
        cls._nodes[node_class.node_type] = node_class

    @classmethod
    def unregister(cls, node_type: str):
        cls._nodes.pop(node_type, None)

    @classmethod
    def get(cls, node_type: str):
        return cls._nodes.get(node_type)

    @classmethod
    def _resolve_tier(cls, node_type: str, source: str) -> str:
        """判断节点档位：built-in / official / custom。"""
        if source and source.startswith("app.nodes."):
            return "built-in"
        official = _load_official_manifest()
        if node_type in official:
            return "official"
        return "custom"

    @classmethod
    def list_nodes(cls) -> list:
        """返回所有已注册节点的信息（供前端渲染）。"""
        result = []
        for ntype, ncls in cls._nodes.items():
            source = ncls.__module__
            result.append({
                "type": ntype,
                "display_name": ncls.display_name,
                "category": ncls.category,
                "params_schema": ncls.params_schema,
                "source": source,
                "tier": cls._resolve_tier(ntype, source),
            })
        return result

    @classmethod
    def get_info(cls, node_type: str):
        cls2 = cls._nodes.get(node_type)
        if not cls2:
            return None
        source = cls2.__module__
        info = {
            "display_name": cls2.display_name,
            "category": cls2.category,
            "params_schema": cls2.params_schema,
            "source": source,
            "tier": cls._resolve_tier(node_type, source),
        }
        # 附加 official 元数据（如果有）
        official = _load_official_manifest()
        if node_type in official:
            info["official_meta"] = official[node_type]
        return info

    @classmethod
    def list_types(cls) -> list:
        return list(cls._nodes.keys())


def _load_official_manifest() -> dict:
    """读取 plugins/official.json，返回 {node_type: meta} 字典（带缓存）。"""
    global _official_cache
    if _official_cache is not None:
        return _official_cache
    manifest_path = Path(__file__).parent.parent.parent / "plugins" / "official.json"
    if not manifest_path.exists():
        _official_cache = {}
        return _official_cache
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        _official_cache = {item["node_type"]: item for item in data if "node_type" in item}
    except Exception as e:
        print(f"[plugins] 读取 official.json 失败: {e}")
        _official_cache = {}
    return _official_cache


def invalidate_official_cache():
    """清除 official.json 缓存（用于热加载场景）。"""
    global _official_cache
    _official_cache = None


def _discover_nodes(module):
    """从模块中自动发现所有 BaseNode 子类。"""
    nodes = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, BaseNode) and obj is not BaseNode:
            nodes.append(obj)
    return nodes


def register_all_nodes():
    """注册所有内置节点。"""
    from app.nodes import resample
    from app.nodes import kline_resample
    from app.nodes import indicators
    from app.nodes import filter
    from app.nodes import sort_group
    from app.nodes import column_ops
    from app.nodes import condition
    from app.nodes import switch
    from app.nodes import custom_python
    from app.nodes import source_fetch
    from app.nodes import target_write
    from app.nodes import range_control
    from app.nodes import contract_list
    from app.nodes import stock_list
    from app.nodes import factor_compute
    from app.nodes import factor_write
    from app.nodes import factor_expression
    from app.nodes import db_query
    from app.nodes import set_variable
    from app.nodes import wait
    from app.nodes import for_each
    from app.nodes import loop
    from app.nodes import try_catch
    from app.nodes import limit
    from app.nodes import merge
    from app.nodes import http_request
    from app.nodes import split_batches
    from app.nodes import datetime_ops
    from app.nodes import aggregation
    from app.nodes import data_convert
    from app.nodes import file_ops

    for mod in [resample, kline_resample, indicators, filter, sort_group, column_ops, condition, switch, custom_python,
                source_fetch, target_write, range_control, contract_list, stock_list,
                factor_compute, factor_write, factor_expression, db_query,
                set_variable, wait, for_each, loop, try_catch, limit, merge, http_request, split_batches, datetime_ops,
                aggregation, data_convert, file_ops]:
        for cls in _discover_nodes(mod):
            NodeRegistry.register(cls)
    _builtin_nodes.clear()
    _builtin_nodes.extend([c.node_type for c in NodeRegistry._nodes.values()])


def discover_custom_plugins(plugins_dir: str = None):
    """从插件目录动态加载自定义节点。"""
    if plugins_dir is None:
        plugins_dir = Path(__file__).parent.parent.parent / "plugins"

    if not os.path.isdir(plugins_dir):
        return []

    loaded = []
    for fname in os.listdir(plugins_dir):
        if not fname.endswith('.py') or fname.startswith('_'):
            continue
        fpath = os.path.join(plugins_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{fname[:-3]}", fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for cls in _discover_nodes(mod):
                NodeRegistry.register(cls)
                loaded.append(cls.node_type)
        except Exception as e:
            print(f"Failed to load plugin {fname}: {e}")
    return loaded


def reload_plugins() -> dict:
    """热加载插件：清空非 built-in 节点，重新扫描 plugins/，刷新 official 缓存。"""
    # 1. 清掉所有非 built-in 注册项
    to_remove = [t for t in NodeRegistry._nodes if t not in _builtin_nodes]
    for t in to_remove:
        NodeRegistry.unregister(t)
    # 2. 刷新 official.json 缓存
    invalidate_official_cache()
    # 3. 重新扫描 plugins/
    loaded = discover_custom_plugins()
    return {
        "removed": to_remove,
        "loaded": loaded,
        "official_count": len(_load_official_manifest()),
    }
