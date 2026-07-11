#!/usr/bin/env python3
"""
测试新的 ADK 处理器架构
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.llm import make_adk_api_call

async def test_adk_processor():
    """测试新的 ADK 处理器架构"""
    print("🧪 开始测试新的 ADK 处理器架构...")
    
    # 准备测试消息
    test_messages = [
        {
            'role': 'user',
            'content': '你好，请简单介绍一下你自己',
            'app_name': 'fufanmanus',
            'user_id': 'test_user_123',
            'session_id': 'test_session_456'
        }
    ]
    
    try:
        print("📡 调用 make_adk_api_call...")
        
        # 调用 ADK API
        response = await make_adk_api_call(
            messages=test_messages,
            model_name="openai/gpt-4o",
            stream=True,
            system_prompt="你是一个友好的AI助手，请用中文回答。"
        )
        
        print("✅ 成功获取 ADK 响应流")
        print("📝 开始处理 ADK 事件:")
        
        # 处理 ADK 事件流
        event_count = 0
        async for event in response:
            event_count += 1
            print(f"🔍 [ADK EVENT DEBUG] 收到第 {event_count} 个 ADK 事件: {type(event)}")
            print(f"🔍 [ADK EVENT DEBUG] 事件内容: {event}")
            
            # 检查事件是否有内容
            if hasattr(event, 'content') and event.content:
                print(f"🔍 [ADK EVENT DEBUG] 事件有内容: {event.content}")
                if hasattr(event.content, 'parts') and event.content.parts:
                    for i, part in enumerate(event.content.parts):
                        if hasattr(part, 'text') and part.text:
                            print(f"🔍 [ADK EVENT DEBUG] 第 {i} 个部分的文本: {part.text}")
        
        print(f"✅ ADK 事件处理完成，共收到 {event_count} 个事件")
        
    except Exception as e:
        print(f"❌ ADK 处理器测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_adk_processor()) 