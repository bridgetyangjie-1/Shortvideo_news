"""
Stub模块 - write_log
"""
import logging
import os

LOG_FILE = "/app/work/logs/bypass/app.log"

def setup_logging(
    log_file: str = LOG_FILE,
    max_bytes: int = 100 * 1024 * 1024,
    backup_count: int = 5,
    log_level: str = "INFO",
    use_json_format: bool = False,
    console_output: bool = True
):
    """配置日志"""
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO if log_level == "INFO" else logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler() if console_output else logging.NullHandler()
        ]
    )

def request_context(*args, **kwargs):
    return {}

__all__ = ['setup_logging', 'request_context', 'LOG_FILE']