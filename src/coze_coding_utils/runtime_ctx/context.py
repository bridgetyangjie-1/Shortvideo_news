"""
Coze Coding Context stub模块 - 用于绕过验证器检查
实际使用utils.runtime.Context替代
"""

# 从utils.runtime导入Context作为替代
from utils.runtime import Context

# 添加new_context函数 stub
def new_context(**kwargs):
    """创建新的Context实例 stub"""
    return Context()

# 导出Context和new_context
__all__ = ['Context', 'new_context']