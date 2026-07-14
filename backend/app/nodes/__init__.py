"""插件节点注册中心。"""
import os
import importlib
import inspect
from pathlib import Path
from app.core.workflow_engine import BaseNode

_builtin_nodes: list = []


class NodeRegistry:
    _nodes: dict = {}

    @classmethod
    def register(cls, node_class: type):
        cls._nodes[node_class.node_type] = node_class

    @classmethod
    def get(cls, node_type: str):
        return cls._nodes.get(node_type)

    @classmethod
    def list_nodes(cls) -> list:
        """返回所有已注册节点的信息（供前端渲染）。"""
        result = []
        for ntype, ncls in cls._nodes.items():
            result.append({
                "type": ntype,
                "display_name": ncls.display_name,
                "category": ncls.category,
                "params_schema": ncls.params_schema,
                "source": ncls.__module__,
            })
        return result

    @classmethod
    def get_info(cls, node_type: str):
        cls2 = cls._nodes.get(node_type)
        if not cls2:
            return None
        return {
            "display_name": cls2.display_name,
            "category": cls2.category,
            "params_schema": cls2.params_schema,
            "source": cls2.__module__,
        }

    @classmethod
    def list_types(cls) -> list:
        return list(cls._nodes.keys())


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
    from app.nodes import indicators
    from app.nodes import filter
    from app.nodes import sort_group
    from app.nodes import column_ops
    from app.nodes import condition
    from app.nodes import custom_python
    from app.nodes import source_fetch
    from app.nodes import target_write
    from app.nodes import range_control
    from app.nodes import contract_list

    for mod in [resample, indicators, filter, sort_group, column_ops, condition, custom_python,
                source_fetch, target_write, range_control, contract_list]:
        for cls in _discover_nodes(mod):
            NodeRegistry.register(cls)
    _builtin_nodes.clear()
    _builtin_nodes.extend([c.node_type for c in NodeRegistry._nodes.values()])


def discover_custom_plugins(plugins_dir: str = None):
    """从插件目录动态加载自定义节点。"""
    if plugins_dir is None:
        plugins_dir = Path(__file__).parent.parent / "plugins"

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
