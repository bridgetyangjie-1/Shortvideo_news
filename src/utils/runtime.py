"""
GitHub Actions专用简化运行时模块
替代coze_coding_utils.runtime_ctx
"""

import os
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel


class Context(BaseModel):
    """简化版Context，用于GitHub Actions环境"""
    user_id: str = "github_actions"
    logger: logging.Logger = logging.getLogger("workflow")
    
    def get(self, key: str, default: Any = None) -> Any:
        return default
    
    def set(self, key: str, value: Any) -> None:
        pass


class Runtime:
    """简化版Runtime包装器"""
    def __init__(self, context: Context):
        self.context = context
    
    @property
    def context(self) -> Context:
        return self._context
    
    @context.setter  
    def context(self, value: Context):
        self._context = value


def get_runtime() -> Runtime:
    """获取运行时实例"""
    ctx = Context()
    return Runtime(ctx)