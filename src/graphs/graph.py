"""
短剧行业研究数据自动更新工作流 - 主图编排
"""
from datetime import datetime
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime

from graphs.state import (
    GlobalState,
    GraphInput,
    GraphOutput,
    ShouldPushInput
)

# 导入所有节点
from graphs.nodes.search_node import search_node
from graphs.nodes.process_node import process_node
from graphs.nodes.enrich_node import enrich_node
from graphs.nodes.actor_ranking_node import actor_ranking_node
from graphs.nodes.industry_node import industry_node
from graphs.nodes.audience_profile_node import audience_profile_node
from graphs.nodes.genre_distribution_node import genre_distribution_node
from graphs.nodes.emotion_analysis_node import emotion_analysis_node
from graphs.nodes.insights_node import insights_node
from graphs.nodes.news_node import news_node
from graphs.nodes.ai_drama_node import ai_drama_node
from graphs.nodes.history_data_node import history_data_node
from graphs.nodes.quality_gate_node import quality_gate_node
from graphs.nodes.alert_node import alert_node
from graphs.nodes.push_node import push_node


# ==================== 条件判断函数 ====================

def should_push_data(state: ShouldPushInput) -> str:
    """
    title: 是否推送数据
    desc: 根据数据质量和处理结果判断是否推送数据
    """
    # 如果数据处理失败，不推送
    if not state.success:
        return "跳过推送"
    
    # 如果数据质量低于60分，不推送
    if state.quality_score < 60:
        return "跳过推送"
    
    return "生成告警"


# ==================== 主图编排 ====================

def create_graph():
    """
    创建短剧行业数据自动更新工作流
    
    工作流架构（V2.0 - 信息降噪版）：
    1. 数据抓取（search_node）- 从多个公开数据源搜索短剧榜单
    2. 行业快讯（news_node）- 搜索过去24小时行业新闻，提炼快讯（并行）
    3. 初步处理（process_node）- 提取基础榜单数据
    4. 数据补充（enrich_node）- 补充演员、标签、描述等详细信息
    5. 演员榜单（actor_ranking_node）- 生成演员人气榜
    6. 行业数据（industry_node）- 获取行业宏观数据
    7. 观众画像（audience_profile_node）- 获取观众画像数据（并行）
    8. 题材分布（genre_distribution_node）- 统计题材分布
    9. 异动点评（insights_node）- 发现数据异动，输出商业建议
    10. 历史数据（history_data_node）- 生成周榜历史和播放趋势
    11. 质量门禁（quality_gate_node）- 统一校验数据质量
    12. 异常监测（alert_node）- 自动生成业务告警
    13. 数据推送（push_node）- 保存 JSON 数据文件
    """
    # 创建状态图
    builder = StateGraph(
        GlobalState, 
        input_schema=GraphInput, 
        output_schema=GraphOutput
    )
    
    # ==================== 添加节点 ====================
    
    # 1. 数据抓取节点
    builder.add_node("search_node", search_node)
    
    # 2. 行业快讯节点（新增）
    builder.add_node(
        "news_node",
        news_node,
        metadata={"type": "agent", "llm_cfg": "config/news_llm_cfg.json"}
    )

    # 2.1 AI 短剧/漫剧看板节点（月度，与 news_node 并行）
    builder.add_node(
        "ai_drama_node",
        ai_drama_node,
        metadata={"type": "agent", "llm_cfg": "config/ai_drama_llm_cfg.json"}
    )
    
    # 3. 初步处理节点（大模型）
    builder.add_node(
        "process_node", 
        process_node, 
        metadata={"type": "agent", "llm_cfg": "config/process_llm_cfg.json"}
    )
    
    # 4. 数据补充节点（大模型）
    builder.add_node(
        "enrich_node", 
        enrich_node, 
        metadata={"type": "agent", "llm_cfg": "config/enrich_llm_cfg.json"}
    )
    
    # 5. 演员榜单生成节点（大模型）
    builder.add_node(
        "actor_ranking_node", 
        actor_ranking_node, 
        metadata={"type": "agent", "llm_cfg": "config/actor_ranking_llm_cfg.json"}
    )
    
    # 6. 行业数据节点（搜索+大模型）
    builder.add_node(
        "industry_node", 
        industry_node, 
        metadata={"type": "agent", "llm_cfg": "config/industry_llm_cfg.json"}
    )
    
    # 6. 观众画像节点（大模型）
    builder.add_node(
        "audience_profile_node", 
        audience_profile_node, 
        metadata={"type": "agent", "llm_cfg": "config/audience_profile_llm_cfg.json"}
    )
    
    # 7. 题材分布节点（统计节点，不需要LLM）
    builder.add_node("genre_distribution_node", genre_distribution_node)
    
    # 8. 情绪分析节点（DeepSeek 推理）
    builder.add_node(
        "emotion_analysis_node",
        emotion_analysis_node,
        metadata={"type": "agent", "llm_cfg": "config/emotion_analysis_llm_cfg.json"}
    )
    
    # 9. 异动点评节点（大模型）- 异动触发式
    builder.add_node(
        "insights_node", 
        insights_node, 
        metadata={"type": "agent", "llm_cfg": "config/insights_llm_cfg.json"}
    )
    
    # 9. 历史数据节点（统计节点，不需要LLM）
    builder.add_node("history_data_node", history_data_node)
    
    # 10. 数据质量门禁节点（新增）
    builder.add_node("quality_gate_node", quality_gate_node)
    
    # 11. 异常监测节点
    builder.add_node("alert_node", alert_node)
    
    # 12. 数据推送节点
    builder.add_node("push_node", push_node)
    
    # ==================== 设置边 ====================
    
    # 设置入口点
    builder.set_entry_point("search_node")
    
    # 主流程边：search → news（并行） + process + ai_drama_node
    builder.add_edge("search_node", "news_node")
    builder.add_edge("search_node", "process_node")
    builder.add_edge("search_node", "ai_drama_node")
    
    # 汇聚：news + process → enrich

    builder.add_edge(["news_node", "process_node"], "enrich_node")
    
    # 主流程
    builder.add_edge("enrich_node", "actor_ranking_node")
    
    # 并行执行：行业数据 和 观众画像
    builder.add_edge("actor_ranking_node", "industry_node")
    builder.add_edge("actor_ranking_node", "audience_profile_node")
    
    # 汇聚：题材分布
    builder.add_edge(["industry_node", "audience_profile_node"], "genre_distribution_node")
    
    # 情绪分析与异动点评并行
    builder.add_edge("genre_distribution_node", "emotion_analysis_node")
    builder.add_edge("genre_distribution_node", "insights_node")
    
    # 汇聚：历史数据
    builder.add_edge(["emotion_analysis_node", "insights_node"], "history_data_node")
    
    # 质量门禁
    builder.add_edge("history_data_node", "quality_gate_node")
    
    # 根据质量门禁结果决定是否推送
    builder.add_conditional_edges(
        "quality_gate_node",
        should_push_data,
        {
            "生成告警": "alert_node",
            "跳过推送": END,
        },
    )
    
    # 异常监测后推送
    builder.add_edge("alert_node", "push_node")

    # AI 看板独立分支汇入 push_node，不阻塞主流程
    builder.add_edge("ai_drama_node", "push_node")
    
    # 结束
    builder.add_edge("push_node", END)
    
    # 编译图
    return builder.compile()


# 创建主图实例
main_graph = create_graph()


if __name__ == "__main__":
    # 测试运行
    from graphs.state import GraphInput
    
    result = main_graph.invoke(GraphInput())
    print(result)
