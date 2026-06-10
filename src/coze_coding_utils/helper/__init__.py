"""
Stub模块 - graph_helper
"""
# Stub实现
class GraphHelper:
    def is_agent_proj(self) -> bool:
        return False
    
    def is_dev_env(self) -> bool:
        return False
    
    def get_graph_instance(self, graph_path: str, ctx=None):
        from graphs.graph import create_graph
        return create_graph()
    
    def get_agent_instance(self, agent_path: str, ctx=None):
        return None

graph_helper = GraphHelper()

__all__ = ['graph_helper', 'GraphHelper']