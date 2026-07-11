"""
使用示例：如何在ADK Agent中使用沙盒Web搜索工具

这个示例展示了如何：
1. 创建沙盒工具工厂
2. 生成ADK兼容的工具
3. 在LlmAgent中使用这些工具
"""

import asyncio
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agentpress.thread_manager import ADKThreadManager
from agent.tools.web_search_tool_adk import SandboxWebSearchToolFactory

async def create_web_search_agent(project_id: str, thread_manager: ADKThreadManager) -> LlmAgent:
    """创建一个具有web搜索和抓取功能的ADK Agent"""
    
    # 1. 创建沙盒工具工厂
    tool_factory = SandboxWebSearchToolFactory(project_id, thread_manager)
    
    # 2. 使用工厂创建ADK工具
    web_search_tool = tool_factory.create_web_search_tool()
    scrape_tool = tool_factory.create_scrape_tool()
    
    # 3. 创建Agent，使用简单的函数工具
    agent = LlmAgent(
        name="WebResearchAssistant",
        model="gemini-2.0-flash",  # 或者你喜欢的其他模型
        instruction="""You are a helpful web research assistant. You can:

1. Search the web using the 'web_search' function to find current information
2. Scrape webpages using the 'scrape_webpage' function to get detailed content

When conducting research:
- Use specific, targeted search queries
- Always scrape multiple relevant URLs at once for efficiency
- Provide comprehensive summaries of the information found
- Cite your sources with URLs

For web searching:
- Use the 'web_search' function with clear, specific queries
- Adjust num_results based on how comprehensive you need the search to be

For webpage scraping:
- Use 'scrape_webpage' with comma-separated URLs from search results
- Always try to scrape multiple relevant pages in a single call
- The scraped content will be saved to files in the sandbox environment

Be thorough and helpful in your research!""",
        tools=[
            web_search_tool,
            scrape_tool
        ]
    )
    
    return agent

async def example_usage():
    """示例：如何使用Web搜索Agent"""
    
    print("=== Web Search Agent Usage Example ===")
    
    # 注意：在实际使用中，你需要提供真实的project_id和thread_manager
    # 这里是演示代码结构
    
    try:
        # 假设你有有效的project_id和thread_manager
        # project_id = "your_project_id"
        # thread_manager = your_adk_thread_manager
        
        # agent = await create_web_search_agent(project_id, thread_manager)
        # 
        # # 创建runner
        # runner = Runner(
        #     app_name="web_research_app",
        #     agent=agent,
        #     session_service=InMemorySessionService()
        # )
        # 
        # # 创建会话
        # session = await runner.session_service.create_session(
        #     app_name="web_research_app",
        #     user_id="test_user"
        # )
        # 
        # # 运行查询
        # user_content = types.Content(
        #     role='user',
        #     parts=[types.Part.from_text(
        #         text="Search for the latest developments in AI agents and then scrape the most relevant articles for detailed information."
        #     )]
        # )
        # 
        # print("🔍 Sending research request to agent...")
        # async for event in runner.run_async(
        #     user_id=session.user_id,
        #     session_id=session.id,
        #     content=user_content
        # ):
        #     if event.type == 'agent_response':
        #         print(f"🤖 Agent Response: {event.content}")
        #     elif event.type == 'tool_call':
        #         print(f"🔧 Tool Call: {event.tool_name} with args: {event.args}")
        #     elif event.type == 'tool_result':
        #         print(f"✅ Tool Result: {event.result}")
        
        print("✅ Example structure created successfully!")
        print("📝 To use this in your application:")
        print("   1. Provide valid project_id and thread_manager")
        print("   2. Uncomment and adapt the code above")
        print("   3. Handle the async events as needed")
        
    except Exception as e:
        print(f"❌ Error in example: {e}")

# 更简单的集成示例：在现有的agent setup中使用
async def integrate_with_existing_agent_setup(project_id: str, thread_manager: ADKThreadManager):
    """展示如何将新工具集成到现有的agent设置中"""
    
    # 创建工具工厂
    web_tool_factory = SandboxWebSearchToolFactory(project_id, thread_manager)
    
    # 获取工具实例
    search_tool = web_tool_factory.create_web_search_tool()
    scrape_tool = web_tool_factory.create_scrape_tool()
    
    # 现在你可以将这些工具添加到任何ADK Agent中
    tools_list = [search_tool, scrape_tool]
    
    # 这些工具现在完全兼容ADK的FunctionTool格式
    # 可以直接用于LlmAgent的tools参数
    
    return tools_list

if __name__ == "__main__":
    asyncio.run(example_usage()) 