from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class WorkflowNode(BaseModel):
    id: str
    name: str
    type: str
    parameters: Dict[str, Any] = {}
    position: List[int] = [0, 0]
    inputs: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []


class WorkflowConfig(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    nodes: List[Dict[str, Any]] = []
    connections: Dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowTestResult(BaseModel):
    success: bool
    output_columns: List[str] = []
    output_rows: int = 0
    node_timings: Dict[str, float] = {}
    error: Optional[str] = None
    sample_data: Optional[List[Dict[str, Any]]] = None
