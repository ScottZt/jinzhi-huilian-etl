"""数据流编排模型 — 支持多数据源 → ETL工作流 → 目标存储。"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class PipelineSourceNode(BaseModel):
    """数据源节点。"""
    id: str
    source_type: str  # tdx | akshare | tushare | mysql | postgresql | csv | ...
    connection_id: str
    params: Dict[str, Any] = {}  # 特定数据源的额外参数


class PipelineTargetNode(BaseModel):
    """目标存储节点。"""
    id: str
    target_type: str  # mysql | postgresql | duckdb | clickhouse | csv | ...
    connection_id: str
    table: str


class PipelineWorkflowNode(BaseModel):
    """ETL工作流节点（可选）。"""
    id: str
    workflow_id: str


class PipelineDefinition(BaseModel):
    """数据流编排定义。"""
    id: Optional[str] = None
    name: str
    description: str = ""
    enabled: bool = True
    cron_expression: Optional[str] = None

    # Pipeline 结构
    sources: List[PipelineSourceNode] = []
    workflow: Optional[PipelineWorkflowNode] = None
    target: Optional[PipelineTargetNode] = None

    # 数据处理配置
    field_mappings: List[Dict[str, str]] = []  # [{source_field, target_field}]
    batch_size: int = 5000
    on_duplicate: str = "ignore"  # ignore | update

    # 元数据
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
