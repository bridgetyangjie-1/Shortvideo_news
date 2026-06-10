"""
Stub模块 - error classifier
"""
class ErrorClassifier:
    def __init__(self):
        pass
    
    def classify(self, error: Exception) -> str:
        return "unknown"

def classify_error(error: Exception) -> str:
    return "unknown"

__all__ = ['ErrorClassifier', 'classify_error']