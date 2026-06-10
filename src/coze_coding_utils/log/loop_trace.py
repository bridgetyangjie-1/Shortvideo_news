"""
Stub模块 - loop_trace
"""
from typing import Any

def init_run_config(graph: Any = None, ctx: Any = None) -> dict:
    return {"configurable": {"thread_id": "test_run"}}

def init_agent_config(agent: Any = None, ctx: Any = None) -> dict:
    return {"configurable": {"thread_id": "test_run"}}

__all__ = ['init_run_config', 'init_agent_config']