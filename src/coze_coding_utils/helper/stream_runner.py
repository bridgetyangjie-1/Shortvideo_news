"""
Stub模块 - stream_runner
"""
from typing import Any, Dict, Iterable

class AgentStreamRunner:
    def stream(self, payload: Dict[str, Any], graph: Any, config: Dict[str, Any], ctx: Any) -> Iterable[Any]:
        yield {"event": "message", "data": {}}

class WorkflowStreamRunner:
    def stream(self, payload: Dict[str, Any], graph: Any, config: Dict[str, Any], ctx: Any) -> Iterable[Any]:
        for chunk in graph.stream(payload, config):
            yield chunk

def agent_stream_handler(*args, **kwargs):
    pass

def workflow_stream_handler(*args, **kwargs):
    pass

class RunOpt:
    pass

__all__ = ['AgentStreamRunner', 'WorkflowStreamRunner', 'agent_stream_handler', 'workflow_stream_handler', 'RunOpt']