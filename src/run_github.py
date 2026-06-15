#!/usr/bin/env python3
"""
GitHub Actions 专用入口文件
用于在GitHub Actions环境中运行短剧看板工作流
"""
import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置环境变量
os.environ['COZE_WORKSPACE_PATH'] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数 - 运行工作流"""
    try:
        logger.info("开始运行短剧看板工作流...")
        
        # 导入工作流
        from graphs.graph import create_graph
        
        # 创建工作流
        graph = create_graph()
        
        # 准备输入数据。GitHub Actions runner 使用 UTC，本项目按北京时间发布每日数据。
        today = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
        input_data = {
            "data_date": today
        }
        
        logger.info(f"数据日期: {today}")
        
        # 运行工作流
        config = {
            "configurable": {
                "thread_id": "github_actions_run"
            }
        }
        
        result = graph.invoke(input_data, config)
        
        logger.info("工作流执行完成！")
        
        # 输出结果摘要（不再重复保存，push_node已保存）
        if result:
            logger.info(f"生成数据日期: {result.get('data_date', 'N/A')}")
            rankings = result.get('rankings', [])
            logger.info(f"榜单数量: {len(rankings)}")
            if rankings:
                # rankings可能是Pydantic对象列表或字典列表
                first_ranking = rankings[0]
                if hasattr(first_ranking, 'title'):
                    logger.info(f"TOP1: {first_ranking.title}")
                elif isinstance(first_ranking, dict):
                    logger.info(f"TOP1: {first_ranking.get('title', 'N/A')}")
            
            # push_node已经保存数据，无需重复保存
            # 只检查保存结果
            output_path = os.path.join(os.environ.get('COZE_WORKSPACE_PATH', os.getcwd()), 'assets', 'data', 'latest.json')
            if os.path.exists(output_path):
                logger.info(f"数据已保存到: {output_path}")
            
            return True
        else:
            logger.error("工作流返回空结果")
            return False
            
    except Exception as e:
        logger.error(f"工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)