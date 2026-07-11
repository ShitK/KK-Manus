import os
import json
import asyncio
import datetime
import uuid
from typing import Optional, Dict, List, Any, AsyncGenerator
from dataclasses import dataclass
import traceback


from agent.github_repo_interview_deterministic_router import (
    build_deterministic_answer_route,
    extract_event_text,
    render_workflow_feedback_markdown,
)
from agent.github_repo_interview_conversation_summary import (
    TOOL_NAME as GITHUB_INTERVIEW_CONVERSATION_SUMMARY_TOOL,
    build_conversation_summary_assistant_response_end,
    build_conversation_summary_from_context,
    render_conversation_summary_markdown,
)
from agent.tools.message_tool import MessageTool
from agent.tools.github_repo_answer_coach import LLMAnswerCoachEngine
from agent.tools.github_repo_interview_workflow_tool import (
    GitHubRepoInterviewWorkflowTool,
    LLMWorkflowStageEngine,
)
from agent.tools.github_repo_interview_session_memory import (
    load_session_memory,
    merge_session_memory,
    upsert_session_memory,
)
from agent.tools.github_repo_interview_intent import normalize_question_category
from agent.tools.github_repo_interview_memory import list_active_memories
from agent.tools.github_repo_interview_vector_memory import (
    LiteLLMVectorMemoryEmbeddingProvider,
    VectorMemoryConfig,
    build_vector_memory_candidate,
    retrieve_vector_memories,
)
from agent.tools.github_repo_interview_tool import GitHubRepoInterviewPrepTool
# from agent.tools.sb_deploy_tool import SandboxDeployTool
# from agent.tools.sb_expose_tool import SandboxExposeTool
# from agent.tools.sandbox_web_search_tool import SandboxWebSearchTool
from dotenv import load_dotenv # type: ignore
from utils.config import config
from utils.constants import MODEL_NAME_ALIASES
from utils.json_helpers import format_for_yield
# from agent.agent_builder_prompt import get_agent_builder_prompt
from agentpress.thread_manager import ThreadManager
from agentpress.tool import ToolResult
from agentpress.response_processor import ProcessorConfig
# from agent.tools.sb_shell_tool import SandboxShellTool
# from agent.tools.sb_files_tool import SandboxFilesTool
#from agent.tools.data_providers_tool import DataProvidersTool
# from agent.tools.expand_msg_tool import ExpandMessageTool
from agent.prompt import get_system_prompt
from agent.gemini_prompt import get_gemini_system_prompt
# from agent.custom_prompt import render_prompt_template
from utils.logger import logger
# from utils.auth_utils import get_account_id_from_thread
# from services.billing import check_billing_status
# from agent.tools.sb_vision_tool import SandboxVisionTool
# from agent.tools.sb_image_edit_tool import SandboxImageEditTool
# from agent.tools.sb_presentation_outline_tool import SandboxPresentationOutlineTool
# from agent.tools.sb_presentation_tool_v2 import SandboxPresentationToolV2
from services.langfuse import langfuse
try:
    from langfuse.client import StatefulTraceClient # type: ignore
except ImportError:
    # 对于 langfuse 3.x 版本，尝试不同的导入路径
    try:
        from langfuse import StatefulTraceClient # type: ignore
    except ImportError:
        # 如果都失败，使用 Any 类型
        from typing import Any
        StatefulTraceClient = Any

# from agent.tools.mcp_tool_wrapper import MCPToolWrapper
# from agent.tools.task_list_tool import TaskListTool
# from agentpress.tool import SchemaType
# from agent.tools.sb_sheets_tool import SandboxSheetsTool
# from agent.tools.sb_web_dev_tool import SandboxWebDevTool

load_dotenv()


_BACKEND_INTERVIEW_ROLE_ALIASES = {
    "ai agent开发工程师",
    "ai agent 开发工程师",
    "ai agent工程师",
    "ai agent 工程师",
    "backend engineer",
    "python backend engineer",
    "python后端工程师",
    "后端工程师",
    "后端开发工程师",
}


def _normalize_vector_memory_target_role(value: Optional[str]) -> Optional[str]:
    role = str(value or "").strip()
    if role.casefold() in _BACKEND_INTERVIEW_ROLE_ALIASES:
        return "后端开发工程师"
    return role or None


def _normalize_vector_memory_category(value: Optional[str]) -> Optional[str]:
    category = str(value or "").strip()
    normalized, _changed = normalize_question_category(category)
    return normalized or category or None


def _assistant_content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
                continue
            content = item.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.append(_assistant_content_to_text(content))
        return "".join(parts)
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        content = value.get("content")
        if isinstance(content, (str, list, dict)):
            return _assistant_content_to_text(content)
        return ""
    return ""


def _merge_recent_messages_with_tool_history(
    recent_messages: List[Dict[str, Any]],
    tool_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep deterministic routing stable when status messages crowd out tool payloads."""
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for message in list(recent_messages or []) + list(tool_messages or []):
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("message_id") or "").strip()
        if message_id:
            if message_id in seen:
                continue
            seen.add(message_id)
        merged.append(message)
    return merged


def _github_interview_workflow_exception_result(
    route: Dict[str, Any],
    error: Exception,
) -> ToolResult:
    route_stage = str(route.get("stage") or "coach_answer")
    question_id = str(route.get("question_id") or "").strip()
    logger.error(
        "Deterministic GitHub interview workflow failed: "
        f"stage={route_stage}, question_id={question_id}, error={error}"
    )
    logger.error("Error details: " + "".join(traceback.format_exception(error)))

    previous_state = route.get("previous_workflow_state")
    data = previous_state.get("data") if isinstance(previous_state, dict) else {}
    selected_question = data.get("selected_question") if isinstance(data, dict) else None
    result_payload: Dict[str, Any] = {
        "tool": "github_repo_interview_workflow",
        "type": "github_repo_interview_workflow",
        "status": "error",
        "input": {
            "stage": route_stage,
            "question_id": question_id,
            "language": route.get("language") or "zh",
        },
        "data": {
            "workflow": {
                "stage": route_stage,
                "status": "error",
            },
        },
        "errors": [
            {
                "code": "workflow_execution_exception",
                "message": "回答点评暂时没有成功生成，请稍后重试。",
                "retryable": True,
            }
        ],
    }
    if isinstance(selected_question, dict):
        result_payload["data"]["selected_question"] = selected_question

    return ToolResult(
        success=False,
        output=json.dumps(result_payload, ensure_ascii=False),
    )


@dataclass
class AgentConfig:
    thread_id: str
    project_id: str
    stream: bool
    native_max_auto_continues: int = 0
    max_iterations: int = 100
    model_name: str = "deepseek/deepseek-v4-flash"
    enable_thinking: Optional[bool] = False
    reasoning_effort: Optional[str] = 'low'
    enable_context_manager: bool = True
    agent_config: Optional[dict] = None
    trace: Optional[StatefulTraceClient] = None # type: ignore
    is_agent_builder: Optional[bool] = False
    target_agent_id: Optional[str] = None
    agent_run_id: Optional[str] = None


class ToolManager:
    def __init__(
        self,
        thread_manager: ThreadManager,
        project_id: str,
        thread_id: str,
        model_name: str = "deepseek/deepseek-v4-flash",
        workflow_memory_context_loader: Optional[Any] = None,
    ):
        self.thread_manager = thread_manager
        self.project_id = project_id
        self.thread_id = thread_id
        self.model_name = model_name
        self.workflow_memory_context_loader = workflow_memory_context_loader
    
    def register_all_tools(self):
        # 测试现有工具注册流程
        logger.info("我现在开始加载工具！！！！")

        from agent.tools.task_list_tool import TaskListTool
        self.thread_manager.add_tool(TaskListTool, project_id=self.project_id, thread_manager=self.thread_manager, thread_id=self.thread_id)
        logger.info("Successfully registered task list tool: TaskListTool (with enhanced registry)")

        self.thread_manager.add_tool(GitHubRepoInterviewPrepTool)
        logger.info(
            "Successfully registered GitHub repo interview prep tool: "
            "GitHubRepoInterviewPrepTool (read-only GitHub metadata, README, tree, "
            "manifests, selected source files, and evidence-backed interview questions)"
        )

        self.thread_manager.add_tool(
            GitHubRepoInterviewWorkflowTool,
            answer_coach_engine=LLMAnswerCoachEngine(model_name=self.model_name),
            follow_up_engine=LLMWorkflowStageEngine("follow_up", model_name=self.model_name),
            summary_engine=LLMWorkflowStageEngine("summary", model_name=self.model_name),
            memory_context_loader=self.workflow_memory_context_loader,
        )
        logger.info(
            "Successfully registered GitHub repo interview workflow tool: "
            "GitHubRepoInterviewWorkflowTool (request-level interview workflow from "
            "existing evidence only; no GitHub reads, local file reads, scoring, "
            "database persistence, or high-risk tool restoration)"
        )
        
        # from agent.tools.sandbox_web_search_tool import SandboxWebSearchTool
        # self.thread_manager.add_tool(SandboxWebSearchTool, project_id=self.project_id, thread_manager=self.thread_manager)

        # self.thread_manager.add_tool(SandboxShellTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxFilesTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxDeployTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxExposeTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxWebSearchTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxVisionTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxImageEditTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxPresentationOutlineTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxPresentationToolV2, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxSheetsTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(SandboxWebDevTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # if config.RAPID_API_KEY:
        #     self.thread_manager.add_tool(DataProvidersTool)
        

        
        # # Add Browser Tool
        # from agent.tools.browser_tool import BrowserTool
        # self.thread_manager.add_tool(BrowserTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
    
    def register_agent_builder_tools(self, agent_id: str):
        pass
        # from agent.tools.agent_builder_tools.agent_config_tool import AgentConfigTool
        # from agent.tools.agent_builder_tools.mcp_search_tool import MCPSearchTool
        # from agent.tools.agent_builder_tools.credential_profile_tool import CredentialProfileTool
        # from agent.tools.agent_builder_tools.workflow_tool import WorkflowTool
        # from agent.tools.agent_builder_tools.trigger_tool import TriggerTool
        # from services.postgresql import DBConnection
        
        # db = DBConnection()
        # self.thread_manager.add_tool(AgentConfigTool, thread_manager=self.thread_manager, db_connection=db, agent_id=agent_id)
        # self.thread_manager.add_tool(MCPSearchTool, thread_manager=self.thread_manager, db_connection=db, agent_id=agent_id)
        # self.thread_manager.add_tool(CredentialProfileTool, thread_manager=self.thread_manager, db_connection=db, agent_id=agent_id)
        # self.thread_manager.add_tool(WorkflowTool, thread_manager=self.thread_manager, db_connection=db, agent_id=agent_id)
        # self.thread_manager.add_tool(TriggerTool, thread_manager=self.thread_manager, db_connection=db, agent_id=agent_id)
    
    def register_custom_tools(self, enabled_tools: Dict[str, Any]):
        pass
        # self.thread_manager.add_tool(ExpandMessageTool, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # self.thread_manager.add_tool(MessageTool)
        # self.thread_manager.add_tool(TaskListTool, project_id=self.project_id, thread_manager=self.thread_manager, thread_id=self.thread_id)

        # def safe_tool_check(tool_name: str) -> bool:
        #     try:
        #         if not isinstance(enabled_tools, dict):
        #             return False
        #         tool_config = enabled_tools.get(tool_name, {})
        #         if not isinstance(tool_config, dict):
        #             return bool(tool_config) if isinstance(tool_config, bool) else False
        #         return tool_config.get('enabled', False)
        #     except Exception:
        #         return False
        
        # if safe_tool_check('sb_shell_tool'):
        #     self.thread_manager.add_tool(SandboxShellTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_files_tool'):
        #     self.thread_manager.add_tool(SandboxFilesTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_deploy_tool'):
        #     self.thread_manager.add_tool(SandboxDeployTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_expose_tool'):
        #     self.thread_manager.add_tool(SandboxExposeTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('web_search_tool'):
        #     self.thread_manager.add_tool(SandboxWebSearchTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_vision_tool'):
        #     self.thread_manager.add_tool(SandboxVisionTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_presentation_tool'):
        #     self.thread_manager.add_tool(SandboxPresentationOutlineTool, project_id=self.project_id, thread_manager=self.thread_manager)
        #     self.thread_manager.add_tool(SandboxPresentationToolV2, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_image_edit_tool'):
        #     self.thread_manager.add_tool(SandboxImageEditTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_sheets_tool'):
        #     self.thread_manager.add_tool(SandboxSheetsTool, project_id=self.project_id, thread_manager=self.thread_manager)
        # if safe_tool_check('sb_web_dev_tool'):
        #     self.thread_manager.add_tool(SandboxWebDevTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)
        # if config.RAPID_API_KEY and safe_tool_check('data_providers_tool'):
        #     self.thread_manager.add_tool(DataProvidersTool)

        
        # if safe_tool_check('browser_tool'):
        #     from agent.tools.browser_tool import BrowserTool
        #     self.thread_manager.add_tool(BrowserTool, project_id=self.project_id, thread_id=self.thread_id, thread_manager=self.thread_manager)


# class MCPManager:
#     def __init__(self, thread_manager: ThreadManager, account_id: str):
#         self.thread_manager = thread_manager
#         self.account_id = account_id
    
#     async def register_mcp_tools(self, agent_config: dict) -> Optional[MCPToolWrapper]:
#         all_mcps = []
        
#         if agent_config.get('configured_mcps'):
#             all_mcps.extend(agent_config['configured_mcps'])
        
#         if agent_config.get('custom_mcps'):
#             for custom_mcp in agent_config['custom_mcps']:
#                 custom_type = custom_mcp.get('customType', custom_mcp.get('type', 'sse'))
                
#                 if custom_type == 'pipedream':
#                     if 'config' not in custom_mcp:
#                         custom_mcp['config'] = {}
                    
#                     if not custom_mcp['config'].get('external_user_id'):
#                         profile_id = custom_mcp['config'].get('profile_id')
#                         if profile_id:
#                             try:
#                                 from pipedream import profile_service
#                                 from uuid import UUID
                                
#                                 profile = await profile_service.get_profile(UUID(self.account_id), UUID(profile_id))
#                                 if profile:
#                                     custom_mcp['config']['external_user_id'] = profile.external_user_id
#                             except Exception as e:
#                                 logger.error(f"Error retrieving external_user_id from profile {profile_id}: {e}")
                    
#                     if 'headers' in custom_mcp['config'] and 'x-pd-app-slug' in custom_mcp['config']['headers']:
#                         custom_mcp['config']['app_slug'] = custom_mcp['config']['headers']['x-pd-app-slug']
                
#                 elif custom_type == 'composio':
#                     qualified_name = custom_mcp.get('qualifiedName')
#                     if not qualified_name:
#                         qualified_name = f"composio.{custom_mcp['name'].replace(' ', '_').lower()}"
                    
#                     mcp_config = {
#                         'name': custom_mcp['name'],
#                         'qualifiedName': qualified_name,
#                         'config': custom_mcp.get('config', {}),
#                         'enabledTools': custom_mcp.get('enabledTools', []),
#                         'instructions': custom_mcp.get('instructions', ''),
#                         'isCustom': True,
#                         'customType': 'composio'
#                     }
#                     all_mcps.append(mcp_config)
#                     continue
                
#                 mcp_config = {
#                     'name': custom_mcp['name'],
#                     'qualifiedName': f"custom_{custom_type}_{custom_mcp['name'].replace(' ', '_').lower()}",
#                     'config': custom_mcp['config'],
#                     'enabledTools': custom_mcp.get('enabledTools', []),
#                     'instructions': custom_mcp.get('instructions', ''),
#                     'isCustom': True,
#                     'customType': custom_type
#                 }
#                 all_mcps.append(mcp_config)
        
#         if not all_mcps:
#             return None
        
#         mcp_wrapper_instance = MCPToolWrapper(mcp_configs=all_mcps)
#         try:
#             await mcp_wrapper_instance.initialize_and_register_tools()
            
#             updated_schemas = mcp_wrapper_instance.get_schemas()
#             for method_name, schema_list in updated_schemas.items():
#                 for schema in schema_list:
#                     self.thread_manager.tool_registry.tools[method_name] = {
#                         "instance": mcp_wrapper_instance,
#                         "schema": schema
#                     }
            
#             logger.info(f"⚡ Registered {len(updated_schemas)} MCP tools (Redis cache enabled)")
#             return mcp_wrapper_instance
#         except Exception as e:
#             logger.error(f"Failed to initialize MCP tools: {e}")
#             return None


class PromptManager:
    @staticmethod
    # async def build_system_prompt(model_name: str, agent_config: Optional[dict], 
    #                               is_agent_builder: bool, thread_id: str, 
    #                               mcp_wrapper_instance: Optional[MCPToolWrapper]) -> dict:
    async def build_system_prompt(model_name: str, agent_config: Optional[dict], 
                                  is_agent_builder: bool, thread_id: str, ) -> dict:    
        if "gemini-2.5-flash" in model_name.lower() and "gemini-2.5-pro" not in model_name.lower():
            default_system_content = get_gemini_system_prompt()
        else:
            default_system_content = get_system_prompt()
        
        # if "anthropic" not in model_name.lower():
        #     sample_response_path = os.path.join(os.path.dirname(__file__), 'sample_responses/1.txt')
        #     with open(sample_response_path, 'r') as file:
        #         sample_response = file.read()
        #     default_system_content = default_system_content + "\n\n <sample_assistant_response>" + sample_response + "</sample_assistant_response>"
        
        # if is_agent_builder:
        #     system_content = get_agent_builder_prompt()
        # elif agent_config and agent_config.get('system_prompt'):
        #     system_content = render_prompt_template(agent_config['system_prompt'].strip())
        # else:
        #    system_content = default_system_content
        system_content = default_system_content
        # if agent_config and (agent_config.get('configured_mcps') or agent_config.get('custom_mcps')) and mcp_wrapper_instance and mcp_wrapper_instance._initialized:
        #     mcp_info = "\n\n--- MCP Tools Available ---\n"
        #     mcp_info += "You have access to external MCP (Model Context Protocol) server tools.\n"
        #     mcp_info += "MCP tools can be called directly using their native function names in the standard function calling format:\n"
        #     mcp_info += '<function_calls>\n'
        #     mcp_info += '<invoke name="{tool_name}">\n'
        #     mcp_info += '<parameter name="param1">value1</parameter>\n'
        #     mcp_info += '<parameter name="param2">value2</parameter>\n'
        #     mcp_info += '</invoke>\n'
        #     mcp_info += '</function_calls>\n\n'
            
        #     mcp_info += "Available MCP tools:\n"
        #     try:
        #         registered_schemas = mcp_wrapper_instance.get_schemas()
        #         for method_name, schema_list in registered_schemas.items():
        #             for schema in schema_list:
        #                 if schema.schema_type == SchemaType.OPENAPI:
        #                     func_info = schema.schema.get('function', {})
        #                     description = func_info.get('description', 'No description available')
        #                     mcp_info += f"- **{method_name}**: {description}\n"
                            
        #                     params = func_info.get('parameters', {})
        #                     props = params.get('properties', {})
        #                     if props:
        #                         mcp_info += f"  Parameters: {', '.join(props.keys())}\n"
                                
        #     except Exception as e:
        #         logger.error(f"Error listing MCP tools: {e}")
        #         mcp_info += "- Error loading MCP tool list\n"
            
        #     mcp_info += "\n🚨 CRITICAL MCP TOOL RESULT INSTRUCTIONS 🚨\n"
        #     mcp_info += "When you use ANY MCP (Model Context Protocol) tools:\n"
        #     mcp_info += "1. ALWAYS read and use the EXACT results returned by the MCP tool\n"
        #     mcp_info += "2. For search tools: ONLY cite URLs, sources, and information from the actual search results\n"
        #     mcp_info += "3. For any tool: Base your response entirely on the tool's output - do NOT add external information\n"
        #     mcp_info += "4. DO NOT fabricate, invent, hallucinate, or make up any sources, URLs, or data\n"
        #     mcp_info += "5. If you need more information, call the MCP tool again with different parameters\n"
        #     mcp_info += "6. When writing reports/summaries: Reference ONLY the data from MCP tool results\n"
        #     mcp_info += "7. If the MCP tool doesn't return enough information, explicitly state this limitation\n"
        #     mcp_info += "8. Always double-check that every fact, URL, and reference comes from the MCP tool output\n"
        #     mcp_info += "\nIMPORTANT: MCP tool results are your PRIMARY and ONLY source of truth for external data!\n"
        #     mcp_info += "NEVER supplement MCP results with your training data or make assumptions beyond what the tools provide.\n"
            
        #     system_content += mcp_info

        now = datetime.datetime.now(datetime.timezone.utc)
        datetime_info = f"\n\n=== CURRENT DATE/TIME INFORMATION ===\n"
        datetime_info += f"Today's date: {now.strftime('%A, %B %d, %Y')}\n"
        datetime_info += f"Current UTC time: {now.strftime('%H:%M:%S UTC')}\n"
        datetime_info += f"Current year: {now.strftime('%Y')}\n"
        datetime_info += f"Current month: {now.strftime('%B')}\n"
        datetime_info += f"Current day: {now.strftime('%A')}\n"
        datetime_info += "Use this information for any time-sensitive tasks, research, or when current date/time context is needed.\n"
        
        system_content += datetime_info

        return {"role": "system", "content": system_content}

class MessageManager:
    """
    消息管理器类
    
    负责构建临时消息，包括浏览器状态和图像上下文信息。
    这些临时消息会在AI处理用户请求时作为上下文信息提供给模型。
    """
    
    def __init__(self, client, thread_id: str, model_name: str, trace: Optional[StatefulTraceClient]): # type: ignore
        """
        初始化消息管理器
        
        Args:
            client: 数据库客户端，用于查询消息表
            thread_id: 线程ID，用于标识特定的对话线程
            model_name: 模型名称，用于判断是否支持图像处理
            trace: 追踪客户端，用于日志记录
        """
        self.client = client
        self.thread_id = thread_id
        self.model_name = model_name
        self.trace = trace
    
    async def build_temporary_message(self) -> Optional[dict]:
        """
        构建临时消息
        
        这个方法会：
        1. 获取最新的浏览器状态信息（包括截图）
        2. 获取最新的图像上下文信息
        3. 将这些信息组合成一个临时消息，供AI模型使用
        
        Returns:
            Optional[dict]: 包含浏览器状态和图像信息的临时消息，如果没有相关信息则返回None
        """
        temp_message_content_list = []  # 存储临时消息的内容列表

        # 获取最新的浏览器状态消息
        latest_browser_state_msg = await self.client.table('messages').select('*').eq('thread_id', self.thread_id).eq('type', 'browser_state').order('created_at', desc=True).limit(1).execute()
        
        if latest_browser_state_msg.data and len(latest_browser_state_msg.data) > 0:
            try:
                # 解析浏览器状态内容
                browser_content = latest_browser_state_msg.data[0]["content"]
                if isinstance(browser_content, str):
                    browser_content = json.loads(browser_content)
                
                # 提取截图信息
                screenshot_base64 = browser_content.get("screenshot_base64")  # Base64编码的截图
                screenshot_url = browser_content.get("image_url")  # 截图的URL地址
                
                # 复制浏览器状态文本，移除截图相关字段
                browser_state_text = browser_content.copy()
                browser_state_text.pop('screenshot_base64', None)
                browser_state_text.pop('image_url', None)

                # 如果有浏览器状态文本信息，添加到临时消息中
                if browser_state_text:
                    temp_message_content_list.append({
                        "type": "text",
                        "text": f"The following is the current state of the browser:\n{json.dumps(browser_state_text, indent=2)}"
                    })
                
                # 检查模型是否支持图像处理（Gemini、Anthropic、OpenAI）
                if 'gemini' in self.model_name.lower() or 'anthropic' in self.model_name.lower() or 'openai' in self.model_name.lower():
                    # 优先使用URL，如果没有则使用Base64
                    if screenshot_url:
                        temp_message_content_list.append({
                            "type": "image_url",
                            "image_url": {
                                "url": screenshot_url,
                                "format": "image/jpeg"
                            }
                        })
                    elif screenshot_base64:
                        temp_message_content_list.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{screenshot_base64}",
                            }
                        })

            except Exception as e:
                logger.error(f"Error parsing browser state: {e}")

        # 获取最新的图像上下文消息
        latest_image_context_msg = await self.client.table('messages').select('*').eq('thread_id', self.thread_id).eq('type', 'image_context').order('created_at', desc=True).limit(1).execute()
        
        if latest_image_context_msg.data and len(latest_image_context_msg.data) > 0:
            try:
                # 解析图像上下文内容
                image_context_content = latest_image_context_msg.data[0]["content"] if isinstance(latest_image_context_msg.data[0]["content"], dict) else json.loads(latest_image_context_msg.data[0]["content"])
                
                # 提取图像信息
                base64_image = image_context_content.get("base64")  # Base64编码的图像
                mime_type = image_context_content.get("mime_type")  # 图像的MIME类型
                file_path = image_context_content.get("file_path", "unknown file")  # 图像文件路径

                # 如果有图像数据，添加到临时消息中
                if base64_image and mime_type:
                    # 添加图像描述文本
                    temp_message_content_list.append({
                        "type": "text",
                        "text": f"Here is the image you requested to see: '{file_path}'"
                    })
                    # 添加图像URL
                    temp_message_content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                        }
                    })

                # 处理完图像上下文后，删除该消息（避免重复使用）
                await self.client.table('messages').delete().eq('message_id', latest_image_context_msg.data[0]["message_id"]).execute()
                
            except Exception as e:
                logger.error(f"Error parsing image context: {e}")

        # 如果有临时消息内容，返回格式化的消息
        if temp_message_content_list:
            return {"role": "user", "content": temp_message_content_list}
        return None

class AgentRunner:

    def __init__(self, config: AgentConfig):
        self.config = config
    
    async def setup(self):
        try:
            if not self.config.trace:
                self.config.trace = langfuse.trace(name="run_agent", session_id=self.config.thread_id, metadata={"project_id": self.config.project_id})
                logger.info(f"Langfuse trace created successfully")
            else:
                logger.info(f"Using existing trace")
     
            # 使用 Google ADK 框架承接服务
            self.thread_manager = ADKThreadManager(
                        trace=self.config.trace, 
                        is_agent_builder=self.config.is_agent_builder or False, 
                        target_agent_id=self.config.target_agent_id, 
                        agent_config=self.config.agent_config
                    )
            logger.info(f"ADKThreadManager created successfully")

            # 初始化数据库客户端
            self.client = await self.thread_manager.db.client
            logger.info(f"Database client initialized successfully")

            # 获取账户ID
            from utils.auth_utils import AuthUtils
            self.account_id = await AuthUtils.get_account_id_from_thread(self.client, self.config.thread_id)
            if not self.account_id: 
                raise ValueError("Could not determine account ID for thread")

            # 获取项目信息
            project = await self.client.table('projects').select('*').eq('project_id', self.config.project_id).execute()
            if not project.data or len(project.data) == 0:
                raise ValueError(f"Project {self.config.project_id} not found")

            project_data = project.data[0]
            sandbox_info = project_data.get('sandbox', {})

            # 处理 sandbox_info 可能是字符串的情况
            if isinstance(sandbox_info, str):
                try:
                    import json
                    sandbox_info = json.loads(sandbox_info)
                except (json.JSONDecodeError, TypeError):
                    sandbox_info = {}

            if not sandbox_info.get('id'):
                # 沙箱是懒加载的，当需要时创建和持久化沙箱元数据
                # 如果沙箱不存在，工具会调用 `_ensure_sandbox()` 来创建和持久化沙箱元数据
                logger.info(f"No sandbox found for project {self.config.project_id}; will create lazily when needed")
            
        except Exception as setup_error:
            logger.error(f"Error details: {traceback.format_exc()}")
            raise setup_error
        
    async def setup_tools(self):
        tool_manager = ToolManager(
            self.thread_manager,
            self.config.project_id,
            self.config.thread_id,
            model_name=self.config.model_name,
            workflow_memory_context_loader=self._load_github_interview_workflow_memory_context,
        )
        if self.config.agent_config and self.config.agent_config.get('is_fufanmanus_default', False):
            tool_manager.register_all_tools()
            logger.info("register all tools success！")

    
    def get_max_tokens(self) -> Optional[int]:
        if "sonnet" in self.config.model_name.lower():
            return 8192
        elif "gpt-4" in self.config.model_name.lower():
            return 4096
        elif "gemini-2.5-pro" in self.config.model_name.lower():
            return 64000
        elif "kimi-k2" in self.config.model_name.lower():
            return 8192
        return None

    async def _save_and_yield_message(
        self,
        thread_run_id: str,
        message_type: str,
        content: Dict[str, Any],
        is_llm_message: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        message = await self.thread_manager.add_message(
            thread_id=self.config.thread_id,
            type=message_type,
            content=content,
            is_llm_message=is_llm_message,
            metadata={
                "thread_run_id": thread_run_id,
                **({"agent_run_id": self.config.agent_run_id} if self.config.agent_run_id else {}),
                **(metadata or {}),
            },
        )
        return format_for_yield(message) if message else None

    async def _load_github_interview_session_memory(self) -> Dict[str, Any]:
        try:
            client = getattr(self, "client", None)
            account_id = getattr(self, "account_id", None)
            thread_id = self.config.thread_id
            if not client or not account_id or not thread_id:
                return {}
            return await load_session_memory(client, account_id, thread_id)
        except Exception as exc:
            logger.warning(f"Failed to load GitHub interview session memory: {exc}")
            return {}

    async def _upsert_github_interview_session_memory(self, payload: Dict[str, Any]) -> None:
        try:
            if not isinstance(payload, dict):
                return
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            patch = data.get("session_memory_patch") if isinstance(data.get("session_memory_patch"), dict) else {}
            if not patch:
                return
            client = getattr(self, "client", None)
            account_id = getattr(self, "account_id", None)
            thread_id = self.config.thread_id
            if not client or not account_id or not thread_id:
                return
            workflow = data.get("workflow") if isinstance(data.get("workflow"), dict) else {}
            await upsert_session_memory(
                client,
                account_id,
                thread_id,
                patch,
                source_agent_run_id=self.config.agent_run_id,
                updated_from_stage=str(workflow.get("current_stage") or "").strip() or None,
            )
        except Exception as exc:
            logger.warning(f"Failed to upsert GitHub interview session memory: {exc}")

    async def _load_github_interview_saved_memories(self) -> List[Dict[str, Any]]:
        try:
            client = getattr(self, "client", None)
            account_id = getattr(self, "account_id", None)
            if not client or not account_id:
                return []
            return await list_active_memories(client, account_id)
        except Exception as exc:
            logger.warning(f"Failed to load GitHub interview saved memories: {exc}")
            return []

    async def _retrieve_github_interview_vector_memories(
        self,
        *,
        query_text: str,
        target_role: Optional[str],
        category: Optional[str],
    ) -> Dict[str, Any]:
        config = VectorMemoryConfig.from_env()
        provider = LiteLLMVectorMemoryEmbeddingProvider(config)
        client = getattr(self, "client", None)
        account_id = getattr(self, "account_id", None)
        if not client or not account_id:
            config = VectorMemoryConfig(
                enabled=False,
                model=config.model,
                api_base=config.api_base,
                match_threshold=config.match_threshold,
                match_count=config.match_count,
                timeout_seconds=config.timeout_seconds,
            )
        return await retrieve_vector_memories(
            client=client,
            provider=provider,
            config=config,
            user_id=str(account_id or ""),
            query_text=query_text,
            target_role=target_role,
            category=category,
        )

    async def _load_github_interview_workflow_memory_context(
        self,
        *,
        query_text: str,
        target_role: Optional[str],
        category: Optional[str],
    ) -> Dict[str, Any]:
        session_memory_context = await self._load_github_interview_session_memory()
        saved_memory_context = await self._load_github_interview_saved_memories()
        effective_target_role = _normalize_vector_memory_target_role(
            target_role or session_memory_context.get("target_role")
        )
        effective_category = _normalize_vector_memory_category(
            category or session_memory_context.get("current_practice_category")
        )
        vector_retrieval = await self._retrieve_github_interview_vector_memories(
            query_text=query_text,
            target_role=effective_target_role,
            category=effective_category,
        )
        return {
            "session_memory_context": session_memory_context,
            "saved_memory_context": saved_memory_context,
            "vector_memory_context": vector_retrieval.get("context") or [],
            "vector_memory_retrieval": vector_retrieval,
        }

    async def _run_deterministic_github_interview_workflow(
        self,
        route: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        thread_run_id = str(uuid.uuid4())
        tool_call_id = f"call_det_{uuid.uuid4().hex[:24]}"
        tool_name = "github_repo_interview_workflow"

        start_message = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "thread_run_start", "thread_run_id": thread_run_id},
        )
        if start_message:
            yield start_message

        assistant_start = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "assistant_response_start"},
        )
        if assistant_start:
            yield assistant_start

        route_stage = str(route.get("stage") or "coach_answer")
        tool_arguments = {
            "stage": route_stage,
            "question_id": route["question_id"],
            "language": route["language"],
            "coach_style": route["coach_style"],
        }
        if route_stage == "summarize":
            assistant_intro = "我会基于已有 GitHub 面试练习状态总结这一轮，并且不会重新读取仓库。"
        elif route_stage == "coach_follow_up":
            assistant_intro = "我会基于已有 GitHub 面试题包点评你的追问回答，并且不会重新读取仓库。"
        else:
            assistant_intro = "我会基于已有 GitHub 面试题包点评你的回答，并且不会重新读取仓库。"
        assistant_call = await self._save_and_yield_message(
            thread_run_id,
            "assistant",
            {
                "role": "assistant",
                "content": assistant_intro,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_arguments, ensure_ascii=False),
                        },
                    }
                ],
            },
            is_llm_message=True,
            metadata={"stream_status": "complete"},
        )
        if assistant_call:
            yield assistant_call

        tool_started = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {
                "role": "assistant",
                "status_type": "tool_started",
                "function_name": tool_name,
                "xml_tag_name": None,
                "message": f"Starting execution of {tool_name}",
                "tool_index": 0,
                "tool_call_id": tool_call_id,
            },
            metadata={
                "tool_call_id": tool_call_id,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_started:
            yield tool_started

        workflow_tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=LLMAnswerCoachEngine(model_name=self.config.model_name),
            follow_up_engine=LLMWorkflowStageEngine("follow_up", model_name=self.config.model_name),
            summary_engine=LLMWorkflowStageEngine("summary", model_name=self.config.model_name),
            memory_context_loader=self._load_github_interview_workflow_memory_context,
        )
        try:
            result = await workflow_tool.github_repo_interview_workflow(**route)
        except Exception as exc:
            result = _github_interview_workflow_exception_result(route, exc)

        if result.success and route_stage == "summarize" and VectorMemoryConfig.from_env().enabled:
            try:
                candidate_payload = json.loads(result.output)
                candidate_data = candidate_payload.get("data") if isinstance(candidate_payload.get("data"), dict) else {}
                patch = candidate_data.get("session_memory_patch") if isinstance(candidate_data.get("session_memory_patch"), dict) else {}
                session_memory_context = (
                    candidate_data.get("session_memory_context")
                    if isinstance(candidate_data.get("session_memory_context"), dict)
                    else {}
                )
                candidate = build_vector_memory_candidate(
                    session_memory=merge_session_memory(session_memory_context, patch),
                    source_thread_id=self.config.thread_id,
                    source_agent_run_id=self.config.agent_run_id,
                )
                if candidate:
                    candidate_data["vector_memory_candidate"] = candidate
                    candidate_payload["data"] = candidate_data
                    result = ToolResult(success=True, output=json.dumps(candidate_payload, ensure_ascii=False, indent=2))
            except Exception as exc:
                logger.warning(f"Failed to build GitHub interview vector memory candidate: {exc}")

        tool_result = await self._save_and_yield_message(
            thread_run_id,
            "tool",
            {"tool_name": tool_name, "result": result.output},
            metadata={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_result:
            yield tool_result

        tool_completed = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {
                "role": "assistant",
                "status_type": "tool_completed" if result.success else "tool_failed",
                "function_name": tool_name,
                "xml_tag_name": None,
                "message": f"Tool {tool_name} {'completed successfully' if result.success else 'failed'}",
                "tool_index": 0,
                "tool_call_id": tool_call_id,
            },
            metadata={
                "tool_call_id": tool_call_id,
                "linked_tool_result_message_id": tool_result.get("message_id") if tool_result else None,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_completed:
            yield tool_completed

        try:
            payload = json.loads(result.output)
        except (TypeError, ValueError):
            payload = {"status": "error", "data": {}}
        if result.success:
            await self._upsert_github_interview_session_memory(payload)
        if result.success:
            final_text = render_workflow_feedback_markdown(payload)
        else:
            errors = payload.get("errors") if isinstance(payload, dict) else None
            first_error = errors[0].get("message") if isinstance(errors, list) and errors and isinstance(errors[0], dict) else ""
            final_text = first_error or "这次回答点评没有成功生成，请稍后重试。"

        final_assistant = await self._save_and_yield_message(
            thread_run_id,
            "assistant",
            {"role": "assistant", "content": final_text},
            is_llm_message=True,
            metadata={"stream_status": "complete"},
        )
        if final_assistant:
            yield final_assistant

        assistant_end = await self._save_and_yield_message(
            thread_run_id,
            "assistant_response_end",
            {"status_type": "assistant_response_end"},
        )
        if assistant_end:
            yield assistant_end

        run_end = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "thread_run_end"},
        )
        if run_end:
            yield run_end

    async def _recent_thread_events_for_summary(self) -> List[Dict[str, Any]]:
        try:
            result = await self.client.table('events').select('*').eq(
                'session_id',
                self.config.thread_id,
            ).order('timestamp', desc=True).limit(80).execute()
            return result.data or []
        except Exception as exc:
            logger.warning(f"Failed to fetch extended events for conversation summary: {exc}")
            return []

    async def _run_deterministic_github_interview_conversation_summary(
        self,
        route: Dict[str, Any],
        historical_messages: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        thread_run_id = str(uuid.uuid4())
        tool_call_id = f"call_det_{uuid.uuid4().hex[:24]}"
        tool_name = GITHUB_INTERVIEW_CONVERSATION_SUMMARY_TOOL

        start_message = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "thread_run_start", "thread_run_id": thread_run_id},
        )
        if start_message:
            yield start_message

        assistant_start = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "assistant_response_start"},
        )
        if assistant_start:
            yield assistant_start

        tool_arguments = {
            "summary_scope": route.get("summary_scope") or "thread_dialogue",
            "language": route.get("language") or "zh",
        }
        assistant_call = await self._save_and_yield_message(
            thread_run_id,
            "assistant",
            {
                "role": "assistant",
                "content": "我会基于当前对话总结这一轮，不会重新读取仓库。",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_arguments, ensure_ascii=False),
                        },
                    }
                ],
            },
            is_llm_message=True,
            metadata={"stream_status": "complete"},
        )
        if assistant_call:
            yield assistant_call

        tool_started = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {
                "role": "assistant",
                "status_type": "tool_started",
                "function_name": tool_name,
                "xml_tag_name": None,
                "message": f"Starting execution of {tool_name}",
                "tool_index": 0,
                "tool_call_id": tool_call_id,
            },
            metadata={
                "tool_call_id": tool_call_id,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_started:
            yield tool_started

        extended_events = await self._recent_thread_events_for_summary()
        events = extended_events or recent_events
        payload = await build_conversation_summary_from_context(
            messages=historical_messages,
            events=events,
            model_name=self.config.model_name,
            language=route.get("language") or "zh",
        )
        if payload.get("status") != "error":
            await self._upsert_github_interview_session_memory(payload)
        output = json.dumps(payload, ensure_ascii=False)
        success = payload.get("status") != "error"

        tool_result = await self._save_and_yield_message(
            thread_run_id,
            "tool",
            {"tool_name": tool_name, "result": output},
            metadata={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_result:
            yield tool_result

        tool_completed = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {
                "role": "assistant",
                "status_type": "tool_completed" if success else "tool_failed",
                "function_name": tool_name,
                "xml_tag_name": None,
                "message": f"Tool {tool_name} {'completed successfully' if success else 'failed'}",
                "tool_index": 0,
                "tool_call_id": tool_call_id,
            },
            metadata={
                "tool_call_id": tool_call_id,
                "linked_tool_result_message_id": tool_result.get("message_id") if tool_result else None,
                "assistant_message_id": assistant_call.get("message_id") if assistant_call else None,
            },
        )
        if tool_completed:
            yield tool_completed

        final_text = render_conversation_summary_markdown(payload)
        final_assistant = await self._save_and_yield_message(
            thread_run_id,
            "assistant",
            {"role": "assistant", "content": final_text},
            is_llm_message=True,
            metadata={"stream_status": "complete"},
        )
        if final_assistant:
            yield final_assistant

        assistant_end = await self._save_and_yield_message(
            thread_run_id,
            "assistant_response_end",
            build_conversation_summary_assistant_response_end(
                payload,
                final_text=final_text,
                fallback_model=self.config.model_name,
            ),
        )
        if assistant_end:
            yield assistant_end

        run_end = await self._save_and_yield_message(
            thread_run_id,
            "status",
            {"status_type": "thread_run_end"},
        )
        if run_end:
            yield run_end
    
    
    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        await self.setup()
        await self.setup_tools()

        # mcp_wrapper_instance = await self.setup_mcp_tools()
        
        # system_message = await PromptManager.build_system_prompt(
        #     self.config.model_name, self.config.agent_config, 
        #     self.config.is_agent_builder, self.config.thread_id, 
        #     mcp_wrapper_instance
        # )

        system_message = await PromptManager.build_system_prompt(
            self.config.model_name, self.config.agent_config, 
            self.config.is_agent_builder, self.config.thread_id, 
        )
        logger.info(f"system_message created successfully")

        # 初始化迭代次数
        iteration_count = 0

        # 初始化继续执行标志
        continue_execution = True

        # 获取最新消息 - 从events表获取
        latest_user_message = await self.client.table('events').select('*').eq('session_id', self.config.thread_id).order('timestamp', desc=True).limit(10).execute()
        logger.info(f"Event table query result: {len(latest_user_message.data) if latest_user_message.data else 0}")

        # 提取用户请求内容
        user_request = None
        if latest_user_message.data and len(latest_user_message.data) > 0:
            logger.info(f"Latest 10 messages author list: {[msg.get('author') for msg in latest_user_message.data]}")
            
            # 找到最新的用户消息
            for i, event in enumerate(latest_user_message.data):
                if event.get('author') == 'user':
                    content = event.get('content', {})
                    timestamp = event.get('timestamp')
                    logger.info(f"Found user message[{i}]: content={content}, timestamp={timestamp}")
                    
                    import json
                    # 解析content字段
                    if isinstance(content, str):
                        try:
                            content = json.loads(content)
                        except json.JSONDecodeError:
                            content = {"content": content}
                    
                    # 提取用户请求
                    if isinstance(content, dict):
                        user_request = extract_event_text(content)
                        logger.info(f"Extracted user request: {user_request}")
                    break
            
            if self.config.trace and user_request:
                self.config.trace.update(input=user_request)

        message_manager = MessageManager(self.client, self.config.thread_id, self.config.model_name, self.config.trace)

        if user_request:
            historical_messages = await self.client.table('messages').select('*').eq(
                'thread_id',
                self.config.thread_id,
            ).order('created_at', desc=True).limit(80).execute()
            historical_tool_messages = await self.client.table('messages').select('*').eq(
                'thread_id',
                self.config.thread_id,
            ).eq(
                'type',
                'tool',
            ).order('created_at', desc=True).limit(40).execute()
            deterministic_route = build_deterministic_answer_route(
                latest_user_text=user_request,
                historical_messages=_merge_recent_messages_with_tool_history(
                    historical_messages.data or [],
                    historical_tool_messages.data or [],
                ),
            )
            if deterministic_route:
                logger.info(
                    "Deterministic GitHub interview route matched: "
                    f"kind={deterministic_route.get('kind') or deterministic_route.get('stage')}, "
                    f"question_id={deterministic_route.get('question_id')}"
                )
                if deterministic_route.get("kind") == "conversation_summary":
                    async for chunk in self._run_deterministic_github_interview_conversation_summary(
                        deterministic_route,
                        historical_messages.data or [],
                        latest_user_message.data or [],
                    ):
                        yield chunk
                else:
                    async for chunk in self._run_deterministic_github_interview_workflow(deterministic_route):
                        yield chunk
                asyncio.create_task(asyncio.to_thread(lambda: langfuse.flush()))
                return

        # 进入循环执行
        while continue_execution and iteration_count < self.config.max_iterations:
            iteration_count += 1          
            logger.info(f"Looping：continue_execution={continue_execution}, iteration_count={iteration_count}, max_iterations={self.config.max_iterations}")
        
            temporary_message = await message_manager.build_temporary_message()
            logger.info(f"temporary_message created successfully: {temporary_message}")
            # max_tokens = self.get_max_tokens()
            
            generation = self.config.trace.generation(name="thread_manager.run_thread") if self.config.trace else None
            try:          
                # 获取可用函数
                available_functions = self.thread_manager.tool_registry.get_available_functions()
                logger.info(f"Get available functions: {list(available_functions.keys())}")
                
                response = await self.thread_manager.run_thread( 
                        thread_id=self.config.thread_id,
                        system_prompt=system_message,
                        stream=self.config.stream,
                        llm_model=self.config.model_name,
                        llm_temperature=0,
                        # llm_max_tokens=max_tokens,
                        llm_max_tokens=1024,
                        tool_choice="auto",
                        available_functions = available_functions,
                        max_xml_tool_calls=0, # 这里不设置限制
                        temporary_message=temporary_message,
                        processor_config=ProcessorConfig(
                            xml_tool_calling=True,
                            native_tool_calling=False,
                            execute_tools=True,
                            execute_on_stream=True,
                            tool_execution_strategy="parallel",
                            xml_adding_strategy="user_message",
                            agent_run_id=self.config.agent_run_id,
                        ),
                        native_max_auto_continues=self.config.native_max_auto_continues,
                        include_xml_examples=True,
                        enable_thinking=self.config.enable_thinking,
                        reasoning_effort=self.config.reasoning_effort,
                        enable_context_manager=self.config.enable_context_manager,
                        generation=generation
                    )
   
                if isinstance(response, dict) and "status" in response and response["status"] == "error":
                    yield response
                    break

                last_tool_call = None
                agent_should_terminate = False
                error_detected = False
                full_response = ""

                try:
                    if hasattr(response, '__aiter__') and not isinstance(response, dict):
                        all_chunk = []
                        index = 0
                        tool_call_assistant_map: Dict[str, str] = {}
                        async for chunk in response:
                            # 拆分包含多个 tool_calls 的最终 assistant 消息，并建立 tool_call_id → assistant_message_id 的映射
                            try:
                                if isinstance(chunk, dict) and chunk.get('type') == 'assistant':
                                    metadata_obj = chunk.get('metadata', {})
                                    if isinstance(metadata_obj, str):
                                        try:
                                            metadata_obj = json.loads(metadata_obj)
                                        except Exception:
                                            metadata_obj = {}
                                    stream_status = metadata_obj.get('stream_status')
                                    if stream_status == 'complete':
                                        content_obj = chunk.get('content', '{}')
                                        if isinstance(content_obj, str):
                                            try:
                                                content_obj = json.loads(content_obj)
                                            except Exception:
                                                content_obj = {}
                                        tool_calls = (
                                            content_obj.get('tool_calls') or []
                                            if isinstance(content_obj, dict)
                                            else []
                                        )
                                        if isinstance(tool_calls, list) and len(tool_calls) > 0:
                                            from uuid import uuid4
                                            assistant_text = _assistant_content_to_text(
                                                content_obj.get('content', '') if isinstance(content_obj, dict) else content_obj
                                            )
                                            from datetime import datetime, timezone, timedelta
                                            base_ts_str = chunk.get('created_at')
                                            try:
                                                base_dt = datetime.fromisoformat(base_ts_str) if isinstance(base_ts_str, str) else datetime.now(timezone.utc)
                                            except Exception:
                                                base_dt = datetime.now(timezone.utc)
                                            for i, tc in enumerate(tool_calls):
                                                # 🔧 生成确定性UUID，与后端拆分逻辑保持一致
                                                tool_call_id = tc.get('id') if isinstance(tc, dict) else f"unknown_{i}"
                                                import hashlib
                                                seed_data = f"assistant_split_{tool_call_id}_{self.config.thread_id}_{i}_v1"
                                                hash_object = hashlib.md5(seed_data.encode())
                                                hex_dig = hash_object.hexdigest()
                                                new_assistant_id = f"{hex_dig[:8]}-{hex_dig[8:12]}-{hex_dig[12:16]}-{hex_dig[16:20]}-{hex_dig[20:]}"
                                                
                                                new_content = {
                                                    "role": "assistant",
                                                    "content": assistant_text if i == 0 else "",
                                                    "tool_calls": [tc]
                                                }
                                                new_chunk = dict(chunk)
                                                new_chunk['message_id'] = new_assistant_id
                                                new_chunk['content'] = json.dumps(new_content)
                                                # 设置严格递增的 created_at，避免前端 key 抖动
                                                try:
                                                    new_dt = base_dt + timedelta(milliseconds=i)
                                                    new_chunk['created_at'] = new_dt.isoformat()
                                                except Exception:
                                                    pass
                                                # 为每页提供稳定顺序号
                                                try:
                                                    metadata_copy = dict(metadata_obj) if isinstance(metadata_obj, dict) else {}
                                                    metadata_copy['tool_index'] = i
                                                    new_chunk['metadata'] = json.dumps(metadata_copy)
                                                except Exception:
                                                    pass
                                                # 记录映射，供后续 tool 结果重写assistant_message_id
                                                try:
                                                    tool_call_id = tc.get('id') if isinstance(tc, dict) else None
                                                    if tool_call_id:
                                                        tool_call_assistant_map[tool_call_id] = new_assistant_id
                                                except Exception:
                                                    pass
                                                all_chunk.append({"index": index, "chunk": new_chunk})
                                                index += 1
                                                yield new_chunk
                                            # 不再下发原始的合并assistant，直接进入下一条chunk
                                            continue
                            except Exception:
                                pass

                            # 重写每个工具结果的 assistant_message_id，指向对应拆分后的 assistant 消息
                            try:
                                if isinstance(chunk, dict) and chunk.get('type') == 'tool':
                                    metadata_obj = chunk.get('metadata', {})
                                    if isinstance(metadata_obj, str):
                                        try:
                                            metadata_obj = json.loads(metadata_obj)
                                        except Exception:
                                            metadata_obj = {}
                                    tool_call_id = metadata_obj.get('tool_call_id') or metadata_obj.get('tool_call')
                                    mapped_assistant_id = tool_call_assistant_map.get(str(tool_call_id)) if tool_call_id else None
                                    if mapped_assistant_id:
                                        metadata_obj['assistant_message_id'] = mapped_assistant_id
                                        chunk['metadata'] = json.dumps(metadata_obj)
                            except Exception:
                                pass
                            if isinstance(chunk, dict) and chunk.get('type') == 'status' and chunk.get('status') == 'error':
                                error_detected = True
                                all_chunk.append({"index": index, "chunk": chunk})
                                index += 1
                                yield chunk
                                continue

                            if chunk.get('type') == 'status':
                                try:
                                    metadata = chunk.get('metadata', {})
                                    if isinstance(metadata, str):
                                        metadata = json.loads(metadata)
                                    content_obj = chunk.get('content', {})
                                    if isinstance(content_obj, str):
                                        try:
                                            content_obj = json.loads(content_obj)
                                        except Exception:
                                            content_obj = {}

                                    if metadata.get('agent_should_terminate'):
                                        agent_should_terminate = True
                                        if content_obj.get('function_name'):
                                            last_tool_call = content_obj['function_name']
                                        elif content_obj.get('xml_tag_name'):
                                            last_tool_call = content_obj['xml_tag_name']

                                    # 将包含 tool_call_id 的状态消息也补充 assistant_message_id，便于前端按页更新进度
                                    tool_call_id_in_status = metadata.get('tool_call_id') or content_obj.get('tool_call_id')
                                    if tool_call_id_in_status:
                                        mapped_assistant_id = tool_call_assistant_map.get(str(tool_call_id_in_status))
                                        if mapped_assistant_id:
                                            metadata['assistant_message_id'] = mapped_assistant_id
                                            chunk['metadata'] = json.dumps(metadata)
                                except Exception:
                                    pass
                            
                            if chunk.get('type') == 'assistant' and 'content' in chunk:
                                try:
                                    content = chunk.get('content', '{}')
                                    if isinstance(content, str):
                                        assistant_content_json = json.loads(content)
                                    else:
                                        assistant_content_json = content

                                    assistant_text = _assistant_content_to_text(
                                        assistant_content_json.get('content', '')
                                        if isinstance(assistant_content_json, dict)
                                        else assistant_content_json
                                    )
                                    full_response += assistant_text
                                    
                                    if isinstance(assistant_text, str):
                                        if '</ask>' in assistant_text or '</complete>' in assistant_text or '</web-browser-takeover>' in assistant_text:
                                            if '</ask>' in assistant_text:
                                                            xml_tool = 'ask'
                                            elif '</complete>' in assistant_text:
                                                            xml_tool = 'complete'
                                            elif '</web-browser-takeover>' in assistant_text:
                                                            xml_tool = 'web-browser-takeover'

                                            last_tool_call = xml_tool
                                    
                                except json.JSONDecodeError:
                                    pass
                                except Exception:
                                    pass

                            all_chunk.append({"index": index, "chunk": chunk})
                            index += 1
                            yield chunk
                    else:
                        error_detected = True

                    if error_detected:
                        if generation:
                            generation.end(output=full_response, status_message="error_detected", level="ERROR")
                        break
                        
                    if agent_should_terminate or last_tool_call in ['ask', 'complete', 'web-browser-takeover']:
                        if generation:
                            generation.end(output=full_response, status_message="agent_stopped")
                        continue_execution = False
                    else:
                        # ✅ 正常完成一轮对话后，也要终止循环（除非需要继续执行任务）
                        continue_execution = False

                except Exception as e:
                    error_msg = f"Error during response streaming: {str(e)}"
                    if generation:
                        generation.end(output=full_response, status_message=error_msg, level="ERROR")
                    yield {
                        "type": "status",
                        "status": "error", 
                        "message": error_msg
                    }
                    break
                     
            except Exception as e:
                error_msg = f"Error running thread: {str(e)}"
                yield {
                    "type": "status",
                    "status": "error", 
                    "message": error_msg
                }
                break
            
            if generation:
                generation.end(output=full_response)

        asyncio.create_task(asyncio.to_thread(lambda: langfuse.flush()))
        #         if isinstance(response, dict) and "status" in response and response["status"] == "error":
        #             yield response
        #             break

        #         last_tool_call = None
        #         agent_should_terminate = False
        #         error_detected = False
        #         full_response = ""
        #         final_response_text = None  # ✅ 用于存储is_final_response的内容
        #         adk_call_completed = False  # ✅ 标记单次ADK调用是否完成

        #         try:
        #             all_chunk = []
        #             if hasattr(response, '__aiter__') and not isinstance(response, dict):
        #                 async for chunk in response:
        #                     print(f"current chunk: {chunk}")
        #                     # ✅ 基于实际事件格式的处理逻辑
        #                     if isinstance(chunk, dict):
        #                         chunk_type = chunk.get('type')
        #                         chunk_content = chunk.get('content', '{}')
        #                         chunk_metadata = chunk.get('metadata', '{}')
                                
        #                         # 解析JSON字符串
        #                         try:
        #                             if isinstance(chunk_content, str):
        #                                 content_data = json.loads(chunk_content)
        #                             else:
        #                                 content_data = chunk_content
                                        
        #                             if isinstance(chunk_metadata, str):
        #                                 metadata_data = json.loads(chunk_metadata)
        #                             else:
        #                                 metadata_data = chunk_metadata
        #                         except json.JSONDecodeError:
        #                             content_data = {}
        #                             metadata_data = {}
                                
        #                         # ✅ 检查assistant消息的完成状态
        #                         if chunk_type == 'assistant' and metadata_data.get('stream_status') == 'complete':
        #                             if content_data.get('content'):
        #                                 final_response_text = content_data['content']
        #                                 logger.info(f"🎯 检测到完整assistant回复: {final_response_text[:100]}...")
                                
        #                         # ✅ 检查finish状态（类似is_final_response）
        #                         elif chunk_type == 'status' and content_data.get('status_type') == 'finish':
        #                             if content_data.get('finish_reason') == 'final':
        #                                 logger.info(f"🏁 检测到final finish状态")
        #                                 # 这表示当前回合的最终响应
                                
        #                         # ✅ 检查thread_run_end（调用完全结束）
        #                         elif chunk_type == 'status' and content_data.get('status_type') == 'thread_run_end':
        #                             logger.info(f"🎯 检测到thread_run_end，ADK调用完全结束")
        #                             adk_call_completed = True
                                
        #                         # ✅ 检查错误状态
        #                         elif chunk_type == 'status' and chunk.get('status') == 'error':
        #                             error_detected = True
        #                             yield chunk
        #                             continue
                        
        #                         # ✅ 检查工具调用和终止条件 (如果还有其他逻辑需要)
        #                         if chunk_type == 'assistant':
        #                             # 🔧 从ADK格式中正确提取文本
        #                             assistant_text = ""
        #                             if content_data.get('content'):
        #                                 # 旧格式：{"content": "text"}
        #                                 assistant_text = str(content_data['content'])
        #                             elif content_data.get('parts'):
        #                                 # ADK格式：{"role": "model", "parts": [{"text": "..."}]}
        #                                 for part in content_data['parts']:
        #                                     if isinstance(part, dict) and 'text' in part:
        #                                         # 🔧 修复：安全处理part['text']，防止list类型导致拼接错误
        #                                         part_text = part['text']
        #                                         if isinstance(part_text, list):
        #                                             part_text = ''.join(str(item) for item in part_text)
        #                                         elif not isinstance(part_text, str):
        #                                             part_text = str(part_text)
        #                                         assistant_text += part_text
                                    
        #                             if assistant_text:
        #                                 # 🔧 修复：确保full_response拼接的类型安全
        #                                 if not isinstance(full_response, str):
        #                                     full_response = str(full_response)
        #                                 if not isinstance(assistant_text, str):
        #                                     assistant_text = str(assistant_text)
        #                                 full_response += assistant_text
                                    
        #                             # 检查XML工具调用
        #                             if isinstance(assistant_text, str):
        #                                 if '</ask>' in assistant_text:
        #                                     last_tool_call = 'ask'
        #                                     agent_should_terminate = True
        #                                 elif '</complete>' in assistant_text:
        #                                     last_tool_call = 'complete' 
        #                                     agent_should_terminate = True
        #                                 elif '</web-browser-takeover>' in assistant_text:
        #                                     last_tool_call = 'web-browser-takeover'
        #                                     agent_should_terminate = True

        #                     yield chunk
                        
        #                 # ✅ 当async for循环结束时，说明事件流耗尽
        #                 if not adk_call_completed:
        #                     adk_call_completed = True
        #                     logger.info(f"🏁 ADK事件流耗尽，单次调用完成")

                      
        #             else:
        #                 error_detected = True
        #             logger.info(f"123all_chunk: {all_chunk}")    
        #         except Exception as stream_error:
        #             error_msg = f"Error during response streaming: {str(stream_error)}"
        #             logger.error(error_msg)
        #             if generation:
        #                 generation.end(output=full_response, status_message=error_msg, level="ERROR")
        #             yield {
        #                 "type": "status",
        #                 "status": "error",
        #                 "message": error_msg
        #             }
        #             break
                    
        #     except Exception as run_error:
        #         error_msg = f"Error running thread: {str(run_error)}"
        #         logger.error(error_msg)
        #         yield {
        #             "type": "status",
        #             "status": "error",
        #             "message": error_msg
        #         }
        #         break
            
        #     # ✅ 外层循环终止判断（基于实际事件）
        #     if error_detected:
        #         logger.info(f"🚨 检测到错误，终止执行")
        #         if generation:
        #             generation.end(output=full_response, status_message="error_detected", level="ERROR")
        #         break
                
        #     # ✅ 基于实际ADK事件的终止判断
        #     if agent_should_terminate or last_tool_call in ['ask', 'complete', 'web-browser-takeover']:
        #         logger.info(f"🛑 Agent明确终止: agent_should_terminate={agent_should_terminate}, last_tool_call={last_tool_call}")
        #         if generation:
        #             generation.end(output=full_response, status_message="agent_stopped")
        #         continue_execution = False
        #         logger.info(f"🛑 设置continue_execution=False，应该退出循环")
                
        #     elif adk_call_completed:
        #         # ✅ ADK调用完成后，继续下一次迭代让Agent执行更多任务
        #         logger.info(f"✅ ADK调用完成，继续执行更多任务 (iteration {iteration_count}/{self.config.max_iterations})")
        #         if final_response_text:
        #             logger.info(f"📝 本轮响应预览: {final_response_text[:200]}...")
        #         # continue_execution保持True，让Agent继续执行任务
                
        #     else:
        #         # ✅ 其他情况
        #         logger.info(f"❓ 未明确的ADK状态 (completed={adk_call_completed}, final_text={bool(final_response_text)})，继续尝试")
            
        #     if generation:
        #         generation.end(output=full_response)

        # # 🔍 循环结束日志
        # logger.info(f"🏁 Agent执行循环结束: continue_execution={continue_execution}, iteration_count={iteration_count}")
        # logger.info(f"🏁 最终状态: max_iterations={self.config.max_iterations}")
        # #                     # ✅ 官方推荐：用is_final_response()获取最终可展示文本
        # #                     if hasattr(chunk, 'is_final_response') and chunk.is_final_response():
        # #                         if hasattr(chunk, 'content') and chunk.content and hasattr(chunk.content, 'parts') and chunk.content.parts:
        # #                             final_response_text = chunk.content.parts[0].text
        # #                             logger.info(f"🎯 检测到final_response: {final_response_text[:100]}...")
                            
        # #                     if isinstance(chunk, dict) and chunk.get('type') == 'status' and chunk.get('status') == 'error':
        # #                         error_detected = True
        # #                         yield chunk
        # #                         continue
                            
        # #                     if chunk.get('type') == 'status':
        # #                         try:
        # #                             metadata = chunk.get('metadata', {})
        # #                             if isinstance(metadata, str):
        # #                                 metadata = json.loads(metadata)
                                    
        # #                             if metadata.get('agent_should_terminate'):
        # #                                 agent_should_terminate = True
                                        
        # #                                 content = chunk.get('content', {})
        # #                                 if isinstance(content, str):
        # #                                     content = json.loads(content)
                                        
        # #                                 if content.get('function_name'):
        # #                                     last_tool_call = content['function_name']
        # #                                 elif content.get('xml_tag_name'):
        # #                                     last_tool_call = content['xml_tag_name']
                                            
        # #                         except Exception:
        # #                             pass
                            
        # #                     if chunk.get('type') == 'assistant' and 'content' in chunk:
        # #                         try:
        # #                             content = chunk.get('content', '{}')
        # #                             if isinstance(content, str):
        # #                                 assistant_content_json = json.loads(content)
        # #                             else:
        # #                                 assistant_content_json = content

        # #                             assistant_text = assistant_content_json.get('content', '')
        # #                             full_response += assistant_text
        # #                             if isinstance(assistant_text, str):
        # #                                 if '</ask>' in assistant_text or '</complete>' in assistant_text or '</web-browser-takeover>' in assistant_text:
        # #                                    if '</ask>' in assistant_text:
        # #                                        xml_tool = 'ask'
        # #                                    elif '</complete>' in assistant_text:
        # #                                        xml_tool = 'complete'
        # #                                    elif '</web-browser-takeover>' in assistant_text:
        # #                                        xml_tool = 'web-browser-takeover'

        # #                                    last_tool_call = xml_tool
                                
        # #                         except json.JSONDecodeError:
        # #                             pass
        # #                         except Exception:
        # #                             pass

        # #                     yield chunk
                        
        # #                 # ✅ 当async for循环结束时，说明这次ADK调用的事件流已耗尽
        # #                 adk_call_completed = True
        # #                 logger.info(f"🏁 ADK事件流耗尽，单次调用完成")
                        
        # #             else:
        # #                 error_detected = True

        # #             if error_detected:
        # #                 logger.info(f"🚨 检测到错误，终止执行")
        # #                 if generation:
        # #                     generation.end(output=full_response, status_message="error_detected", level="ERROR")
        # #                 break
                        
        # #             # ✅ 基于官方建议的外层循环终止判断
        # #             if agent_should_terminate or last_tool_call in ['ask', 'complete', 'web-browser-takeover']:
        # #                 logger.info(f"🛑 Agent明确终止: agent_should_terminate={agent_should_terminate}, last_tool_call={last_tool_call}")
        # #                 if generation:
        # #                     generation.end(output=full_response, status_message="agent_stopped")
        # #                 continue_execution = False
        # #                 logger.info(f"🛑 设置continue_execution=False，应该退出循环")
        # #             elif adk_call_completed and final_response_text:
        # #                 # ✅ ADK调用完成且有最终响应文本，通常表示一轮完整对话结束
        # #                 logger.info(f"✅ ADK调用完成且有最终响应，默认终止外层循环")
        # #                 logger.info(f"📝 最终响应预览: {final_response_text[:200]}...")
        # #                 continue_execution = False
        # #             elif adk_call_completed and not final_response_text:
        # #                 # ✅ ADK调用完成但没有最终响应文本，可能需要继续
        # #                 logger.info(f"⚠️ ADK调用完成但无最终响应文本，继续下一次迭代")
        # #                 # continue_execution保持True，继续下一次迭代
        # #             else:
        # #                 # ✅ 其他情况，可能是ADK内部错误或异常状态
        # #                 logger.info(f"❓ 未明确的ADK状态 (completed={adk_call_completed}, final_text={bool(final_response_text)})，继续尝试")

        # #         except Exception as e:
        # #             error_msg = f"Error during response streaming: {str(e)}"
        # #             if generation:
        # #                 generation.end(output=full_response, status_message=error_msg, level="ERROR")
        # #             yield {
        # #                 "type": "status",
        # #                 "status": "error",
        # #                 "message": error_msg
        # #             }
        # #             break
                    
        # #     except Exception as e:
        # #         error_msg = f"Error running thread: {str(e)}"
        # #         yield {
        # #             "type": "status",
        # #             "status": "error",
        # #             "message": error_msg
        # #         }
        # #         break
            
        # #     if generation:
        # #         generation.end(output=full_response)

        # # # 🔍 循环结束日志
        # # logger.info(f"🏁 Agent执行循环结束: continue_execution={continue_execution}, iteration_count={iteration_count}")
        # # logger.info(f"🏁 最终状态: max_iterations={self.config.max_iterations}")

        # asyncio.create_task(asyncio.to_thread(lambda: langfuse.flush()))


    # async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        # """运行Agent，支持ADK和ThreadManager两种模式"""
        # print(f"🚀 ===== AgentRunner.run()开始执行 =====")
        # try:
        #     # 检查使用哪种模式
        #     if self.adk_runner and self.adk_session:
        #         print(f"  🔄 使用ADK模式执行...")
        #         async for event in self._run_with_adk():
        #             yield event
        #     elif self.thread_manager:
        #         print(f"  🔄 使用ThreadManager模式执行...")
        #         async for event in self._run_with_thread_manager():
        #             yield event
        #     else:
        #         raise RuntimeError("Neither ADK Runner nor ThreadManager initialized. Call setup() first.")
            
        #     print(f"  ✅ AgentRunner.run()执行完成")
            
        # except Exception as run_error:
        #     print(f"  ❌ AgentRunner.run()执行失败: {run_error}")
        #     print(f"  📋 错误详情: {traceback.format_exc()}")
        #     # 返回错误事件
        #     yield {
        #         "type": "error",
        #         "content": f"Agent execution failed: {str(run_error)}",
        #         "metadata": {"error": str(run_error)}
        #     }
    
    async def _run_with_adk(self) -> AsyncGenerator[Dict[str, Any], None]:
        """使用ADK Runner执行"""
        try:
            print(f"  📝 准备用户输入...")
            # 准备用户输入内容
            user_content = types.Content(
                role='user',
                parts=[types.Part.from_text(text=self.config.user_message or "Hello")]
            )
            print(f"  ✅ 用户输入准备完成")
            
            print(f"  🔄 开始ADK Runner执行...")
            # 使用ADK Runner执行
            async for event in self.adk_runner.run_async(
                user_id=self.adk_session.user_id,
                content=user_content,
                session_id=self.adk_session.id
            ):
                print(f"  📨 收到ADK事件: {event.type}")
                
                # 将ADK事件转换为你的格式
                converted_event = self._convert_adk_event_to_format(event)
                if converted_event:
                    yield converted_event
                
                # 检查是否完成
                if event.type == "assistant_response_end":
                    print(f"  ✅ ADK执行完成")
                    break
                    
        except Exception as adk_error:
            print(f"  ❌ ADK执行失败: {adk_error}")
            yield {
                "type": "error",
                "content": f"ADK execution failed: {str(adk_error)}",
                "metadata": {"error": str(adk_error)}
            }
    
    async def _run_with_thread_manager(self) -> AsyncGenerator[Dict[str, Any], None]:
        """使用ThreadManager执行（回退模式）"""
        try:
            print(f"  📝 准备ThreadManager执行...")
            
            # 构建临时消息
            temporary_message = None
            if self.client:
                try:
                    message_manager = MessageManager(
                        self.client, 
                        self.config.thread_id, 
                        self.config.model_name, 
                        self.config.trace
                    )
                    temporary_message = await message_manager.build_temporary_message()
                    if temporary_message:
                        print(f"  ✅ 临时消息构建成功")
                    else:
                        print(f"  ℹ️ 没有临时消息")
                except Exception as msg_error:
                    print(f"  ⚠️ 构建临时消息失败: {msg_error}")
                    temporary_message = None
            
            # 构建系统提示
            system_prompt = PromptManager.build_system_prompt(
                model_name=self.config.model_name,
                agent_config=self.config.agent_config,
                is_agent_builder=self.config.is_agent_builder or False,
                thread_id=self.config.thread_id
            )
            
            # 使用原有的ThreadManager逻辑
            response = await self.thread_manager.run_thread(
                thread_id=self.config.thread_id,
                system_prompt=system_prompt,
                stream=self.config.stream,
                temporary_message=temporary_message,
                llm_model=self.config.model_name,
                enable_thinking=self.config.enable_thinking,
                reasoning_effort=self.config.reasoning_effort,
                enable_context_manager=self.config.enable_context_manager
            )
            
            # 处理响应
            if response:
                yield {
                    "type": "assistant",
                    "content": {"role": "assistant", "content": str(response)},
                    "metadata": {"thread_run_id": self.config.agent_run_id}
                }
            
            print(f"  ✅ ThreadManager执行完成")
            
        except Exception as tm_error:
            print(f"  ❌ ThreadManager执行失败: {tm_error}")
            yield {
                "type": "error",
                "content": f"ThreadManager execution failed: {str(tm_error)}",
                "metadata": {"error": str(tm_error)}
            }
    
    def _convert_adk_event_to_format(self, adk_event) -> Optional[Dict[str, Any]]:
        """将ADK事件转换为你的格式"""
        try:
            if adk_event.type == "assistant_response_start":
                return {
                    "type": "status",
                    "content": {"status_type": "assistant_response_start"},
                    "metadata": {"thread_run_id": self.config.agent_run_id}
                }
            
            elif adk_event.type == "assistant_response":
                # 处理助手响应
                content = adk_event.content
                if content and hasattr(content, 'parts'):
                    text_content = ""
                    for part in content.parts:
                        if hasattr(part, 'text'):
                            # 🔧 确保类型安全，防止字符串拼接错误
                            part_text = part.text
                            if isinstance(part_text, list):
                                part_text = ''.join(str(item) for item in part_text)
                            elif not isinstance(part_text, str):
                                part_text = str(part_text)
                            text_content += part_text
                    
                    return {
                        "type": "assistant",
                        "content": {"role": "assistant", "content": text_content},
                        "metadata": {"stream_status": "chunk", "thread_run_id": self.config.agent_run_id}
                    }
            
            elif adk_event.type == "tool_started":
                # 处理工具调用
                return {
                    "type": "status",
                    "content": {
                        "role": "assistant",
                        "status_type": "tool_started",
                        "tool_name": adk_event.tool_name,
                        "tool_args": adk_event.tool_args
                    },
                    "metadata": {"thread_run_id": self.config.agent_run_id}
                }
            
            elif adk_event.type == "tool_result":
                # 处理工具结果
                return {
                    "type": "tool",
                    "content": {
                        "role": "tool",
                        "tool_name": adk_event.tool_name,
                        "result": adk_event.result
                    },
                    "metadata": {"thread_run_id": self.config.agent_run_id}
                }
            
            elif adk_event.type == "assistant_response_end":
                # 处理响应结束
                return {
                    "type": "status",
                    "content": {"status_type": "assistant_response_end"},
                    "metadata": {"thread_run_id": self.config.agent_run_id}
                }
            
            return None
            
        except Exception as convert_error:
            print(f"  ⚠️ 事件转换失败: {convert_error}")
            return None

from agentpress.adk_thread_manager import ADKThreadManager
from typing import  Union


async def run_agent(
    thread_id: str,
    project_id: str,
    stream: bool,
    # thread_manager: Optional[Union[ThreadManager, ADKThreadManager]] = None,  
    native_max_auto_continues: int = 0,
    max_iterations: int = 100,
    model_name: str = "deepseek/deepseek-v4-flash",
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = 'low',
    enable_context_manager: bool = True,
    agent_config: Optional[dict] = None,    
    trace: Optional[StatefulTraceClient] = None, # type: ignore
    is_agent_builder: Optional[bool] = False,
    target_agent_id: Optional[str] = None,
    agent_run_id: Optional[str] = None,
):
    logger.info(f"Using thread_id: {thread_id}")
    logger.info(f"Using project_id: {project_id}")
    logger.info(f"Using stream: {stream}")
    logger.info(f"Using model_name: {model_name}")
    if agent_config:
        logger.info(f"Using agent_config: {agent_config.get('name', 'Unknown')}")
    else:
        logger.info(f"Using agent_config: None")

    effective_model = model_name
    if model_name == "deepseek/deepseek-v4-flash" and agent_config and agent_config.get('model'):
        agent_config_model = agent_config['model']
        resolved_agent_config_model = MODEL_NAME_ALIASES.get(agent_config_model, agent_config_model)
        if resolved_agent_config_model != model_name:
            effective_model = resolved_agent_config_model
            logger.info(f"Using model from agent config: {effective_model}")
        else:
            logger.info(f"Using default model after resolving legacy agent config model: {effective_model}")
    elif model_name != "deepseek/deepseek-v4-flash":
        logger.info(f"Using user-selected model: {effective_model}")
    else:
        logger.info(f"Using default model: {effective_model}")
    
    logger.info(f"Creating AgentConfig")

    config = AgentConfig(
        thread_id=thread_id,
        project_id=project_id,
        stream=stream,
        native_max_auto_continues=native_max_auto_continues, # 控制 AI Agent 自动继续对话的最大次数
        max_iterations=max_iterations, # Agent 最大迭代次数
        model_name=effective_model,
        enable_thinking=enable_thinking,  # 是否启用思考
        reasoning_effort=reasoning_effort,  # 思考力度
        enable_context_manager=enable_context_manager,
        agent_config=agent_config,  # Agent 配置
        trace=trace,
        is_agent_builder=is_agent_builder,  # 是否是 Agent 构建器
        target_agent_id=target_agent_id,  # 目标 Agent ID
        agent_run_id=agent_run_id,
    )

    # 创建 Runner 
    runner = AgentRunner(config)
    logger.info(f"AgentRunner created successfully: {runner}")
    
    try:
        logger.info(f"Starting to run runner.run()")
        async for chunk in runner.run():
            yield chunk
    except Exception as run_error:
        logger.error(f"runner.run() failed: {run_error}")
        logger.error(f"Error details: {traceback.format_exc()}")
        raise run_error
