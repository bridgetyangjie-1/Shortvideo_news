#!/usr/bin/env python3
"""
短剧行业数据工作流 - 本地运行脚本
用于绕过Coze平台认证问题，直接生成数据
"""
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# 设置路径
workspace_path = Path(__file__).parent
sys.path.insert(0, str(workspace_path / "src"))

from graphs.graph import main_graph
from graphs.state import GraphInput

def run_workflow(data_date=None):
    """
    运行工作流并返回结果
    
    Args:
        data_date: 数据日期 (YYYY-MM-DD)，不传则使用当前日期
    
    Returns:
        dict: 工作流执行结果
    """
    if data_date is None:
        data_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"正在抓取 {data_date} 的短剧榜单数据...")
    
    # 调用工作流
    result = main_graph.invoke(GraphInput(data_date=data_date))
    
    return result

def save_to_json(result, output_path=None):
    """
    保存结果到JSON文件
    
    Args:
        result: 工作流结果
        output_path: 输出路径，不传则保存到assets目录
    """
    if output_path is None:
        output_path = workspace_path / "assets" / f"short_drama_data_{result['data_date']}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 数据已保存到: {output_path}")
    return output_path

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='短剧行业数据工作流')
    parser.add_argument('-d', '--date', help='数据日期 (YYYY-MM-DD)', default=None)
    parser.add_argument('-o', '--output', help='输出文件路径', default=None)
    parser.add_argument('--webhook', help='推送数据的Webhook URL', default=None)
    
    args = parser.parse_args()
    
    # 如果提供了webhook URL，设置环境变量
    if args.webhook:
        os.environ['SHORT_DRAMA_WEBHOOK_URL'] = args.webhook
        print(f"使用Webhook URL: {args.webhook}")
    
    # 运行工作流
    result = run_workflow(args.date)
    
    # 打印摘要
    print("\n" + "="*60)
    print(f"📊 数据生成完成")
    print("="*60)
    print(f"生成时间: {result['generated_at']}")
    print(f"数据日期: {result['data_date']}")
    print(f"数据质量: {result['quality_score']} 分")
    print(f"榜单数量: {len(result['rankings'])} 条")
    print(f"成功状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    
    if result['error_message']:
        print(f"错误信息: {result['error_message']}")
    
    print("\n榜单TOP 3:")
    for i, item in enumerate(result['rankings'][:3], 1):
        print(f"  {i}. {item['title']} - {item['views']}")
    
    # 保存结果
    output_path = save_to_json(result, args.output)
    
    # 返回结果
    return result

if __name__ == '__main__':
    main()
