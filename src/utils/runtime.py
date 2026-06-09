"""
GitHub Actions专用简化运行时模块
替代coze_coding_utils.runtime_ctx
"""

import os
import logging
from typing import Any, Dict, Optional, TypeVar, Generic
from pydantic import BaseModel

# 泛型类型变量
T = TypeVar('T')


class Context(BaseModel):
    """简化版Context，用于GitHub Actions环境"""
    model_config = {"arbitrary_types_allowed": True}
    
    user_id: str = "github_actions"
    logger: logging.Logger = logging.getLogger("workflow")
    
    def get(self, key: str, default: Any = None) -> Any:
        return default
    
    def set(self, key: str, value: Any) -> None:
        pass


# 使用langgraph.runtime的Runtime，让它支持泛型
from langgraph.runtime import Runtime as LangGraphRuntime

# Runtime已经是泛型类，直接使用即可
# Runtime[Context] 表示Runtime的context属性是Context类型

# 为了兼容性，导出Runtime和Context
__all__ = ['Context', 'Runtime']


def get_runtime() -> LangGraphRuntime[Context]:
    """获取运行时实例"""
    ctx = Context()
    return LangGraphRuntime(context=ctx)