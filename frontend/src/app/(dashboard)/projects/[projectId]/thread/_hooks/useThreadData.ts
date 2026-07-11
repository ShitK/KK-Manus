import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Project } from '@/lib/api';
import { useThreadQuery } from '@/hooks/react-query/threads/use-threads';
import { useMessagesQuery } from '@/hooks/react-query/threads/use-messages';
import { useProjectQuery } from '@/hooks/react-query/threads/use-project';
import { useAgentRunsQuery } from '@/hooks/react-query/threads/use-agent-run';
import { ApiMessageType, UnifiedMessage, AgentStatus } from '../_types';

interface UseThreadDataReturn {
  messages: UnifiedMessage[];
  setMessages: React.Dispatch<React.SetStateAction<UnifiedMessage[]>>;
  project: Project | null;
  sandboxId: string | null;
  projectName: string;
  agentRunId: string | null;
  setAgentRunId: React.Dispatch<React.SetStateAction<string | null>>;
  agentStatus: AgentStatus;
  setAgentStatus: React.Dispatch<React.SetStateAction<AgentStatus>>;
  isLoading: boolean;
  error: string | null;
  initialLoadCompleted: boolean;
  threadQuery: ReturnType<typeof useThreadQuery>;
  messagesQuery: ReturnType<typeof useMessagesQuery>;
  projectQuery: ReturnType<typeof useProjectQuery>;
  agentRunsQuery: ReturnType<typeof useAgentRunsQuery>;
}

export function useThreadData(threadId: string, projectId: string): UseThreadDataReturn {
  const [messages, setMessages] = useState<UnifiedMessage[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState<string>('');
  const [agentRunId, setAgentRunId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus>('idle');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // 🎯 添加流式保护标志
  const isStreamingOrRecentlyStreamedRef = useRef(false);
  
  const initialLoadCompleted = useRef<boolean>(false);
  const messagesLoadedRef = useRef(false);
  const agentRunsCheckedRef = useRef(false);
  const hasInitiallyScrolled = useRef<boolean>(false);
  

  const threadQuery = useThreadQuery(threadId);
  const messagesQuery = useMessagesQuery(threadId);

  // 调试React Query状态
  console.log('🔎 [useThreadData] messagesQuery完整状态:', {
    data: messagesQuery.data,
    status: messagesQuery.status,
    isLoading: messagesQuery.isLoading,
    isFetching: messagesQuery.isFetching,
    isError: messagesQuery.isError,
    error: messagesQuery.error,
    enabled: !!threadId,
    threadId
  });
  const projectQuery = useProjectQuery(projectId);
  const agentRunsQuery = useAgentRunsQuery(threadId);
  
  // 🎯 管理流式保护标志
  useEffect(() => {
    if (agentStatus === 'running' || agentStatus === 'connecting') {
      console.log('🛡️ [useThreadData] 启用流式保护 - agentStatus:', agentStatus);
      isStreamingOrRecentlyStreamedRef.current = true;
    } else if (agentStatus === 'idle') {
      // 延迟清除保护标志，给消息状态稳定一些时间
      console.log('⏰ [useThreadData] 5秒后清除流式保护');
      setTimeout(() => {
        console.log('🔓 [useThreadData] 清除流式保护');
        isStreamingOrRecentlyStreamedRef.current = false;
      }, 5000); // 增加到5秒
    }
  }, [agentStatus]);
  
  // (debug logs removed)

  useEffect(() => {
    let isMounted = true;
    
    // Reset refs when thread changes
    agentRunsCheckedRef.current = false;
    messagesLoadedRef.current = false;
    initialLoadCompleted.current = false;
    
    // Clear messages on thread change; fresh data will set messages
    setMessages([]);

    async function initializeData() {
      if (!initialLoadCompleted.current) setIsLoading(true);
      setError(null);
      try {
        if (!threadId) throw new Error('Thread ID is required');

        if (threadQuery.isError) {
          throw new Error('Failed to load thread data: ' + threadQuery.error);
        }
        if (!isMounted) return;

        if (projectQuery.data) {
          setProject(projectQuery.data);
          if (typeof projectQuery.data.sandbox === 'string') {
            setSandboxId(projectQuery.data.sandbox);
          } else if (projectQuery.data.sandbox?.id) {
            setSandboxId(projectQuery.data.sandbox.id);
          }

          setProjectName(projectQuery.data.name || '');
        }

        if (messagesQuery.data && !messagesLoadedRef.current) {
          console.log('🔍 [useThreadData] 接收到消息数据:', messagesQuery.data);
          console.log('🔍 [useThreadData] 消息数据详细分析:', {
            isArray: Array.isArray(messagesQuery.data),
            length: messagesQuery.data?.length,
            types: messagesQuery.data?.map((m: any) => m.type),
            messageIds: messagesQuery.data?.map((m: any) => m.message_id || m.id),
            rawData: JSON.stringify(messagesQuery.data, null, 2)
          });

          const unifiedMessages = (messagesQuery.data || [])
            .filter((msg: any) => msg.type !== 'status')
            .map((msg: ApiMessageType) => ({
              message_id: msg.message_id || null,
              thread_id: msg.thread_id || threadId,
              type: (msg.type || 'system') as UnifiedMessage['type'],
              is_llm_message: Boolean(msg.is_llm_message),
              content: msg.content || '',
              metadata: msg.metadata || '{}',
              created_at: msg.created_at || new Date().toISOString(),
              updated_at: msg.updated_at || new Date().toISOString(),
              agent_id: (msg as any).agent_id,
              agents: (msg as any).agents,
            }));
            
          console.log('🔍 [useThreadData] 过滤后的消息:', unifiedMessages);

          // Merge with any local messages that are not present in server data yet
          const serverIds = new Set(
            unifiedMessages.map((m) => m.message_id).filter(Boolean) as string[],
          );
          const localExtras = (messages || []).filter(
            (m) =>
              !m.message_id ||
              (typeof m.message_id === 'string' && m.message_id.startsWith('temp-')) ||
              !serverIds.has(m.message_id as string),
          );
          const mergedMessages = [...unifiedMessages, ...localExtras].sort((a, b) => {
            const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
            return aTime - bTime;
          });

          console.log('🔍 [useThreadData] 合并后的消息:', mergedMessages);
          setMessages(mergedMessages);
          console.log('🔍 [useThreadData] 消息已设置到state');
          // Messages set only from server merge; no cross-thread cache
          messagesLoadedRef.current = true;

          if (!hasInitiallyScrolled.current) {
            hasInitiallyScrolled.current = true;
          }
        }

        if (agentRunsQuery.data && !agentRunsCheckedRef.current && isMounted) {
          console.log('🔍 [useThreadData] Processing agent runs:', {
            total: agentRunsQuery.data.length,
            statuses: agentRunsQuery.data.map(r => ({ id: r.id, status: r.status }))
          });
          
          agentRunsCheckedRef.current = true;
          
          // Check for any running agents - only connect to RUNNING agents!
          const runningRuns = agentRunsQuery.data.filter(r => r.status === 'running');
          console.log('🏃 [useThreadData] Running agent runs:', runningRuns.length);
          
          if (runningRuns.length > 0) {
            const latestRunning = runningRuns[0]; // Use first running agent
            console.log('✅ [useThreadData] Found running agent:', latestRunning.id);
            setAgentRunId(latestRunning.id);
            setAgentStatus((current) => {
              if (current !== 'running') {
                console.log('✅ [useThreadData] Changed agentStatus to RUNNING');
                return 'running';
              }
              return current;
            });
          } else {
            // For historical conversations, don't set any agentRunId
            console.log('💤 [useThreadData] No running agents found - this is likely a historical conversation');
            setAgentStatus((current) => {
              if (current !== 'idle') {
                console.log('✅ [useThreadData] Changed agentStatus to IDLE');
                return 'idle';
              }
              return current;
            });
            // Explicitly clear any previous agentRunId to prevent streaming attempts
            setAgentRunId(null);
          }
        }

        if (threadQuery.data && messagesQuery.data && agentRunsQuery.data) {
          initialLoadCompleted.current = true;
          setIsLoading(false);
          // Removed time-based final check to avoid incorrectly forcing idle while a stream is active
        }

      } catch (err) {
        console.error('Error loading thread data:', err);
        if (isMounted) {
          const errorMessage =
            err instanceof Error ? err.message : 'Failed to load thread';
          setError(errorMessage);
          toast.error(errorMessage);
          setIsLoading(false);
        }
      }
    }

    if (threadId) {
      initializeData();
    }

    return () => {
      isMounted = false;
    };
  }, [
    threadId,
    threadQuery.data,
    threadQuery.isError,
    threadQuery.error,
    projectQuery.data,
    messagesQuery.data,
    agentRunsQuery.data
  ]);

  // Force message reload when thread changes or new data arrives
  useEffect(() => {
    console.log('📡 [useThreadData] useEffect triggered:', {
      messagesQueryDataLength: messagesQuery.data?.length || 0,
      messagesQueryStatus: messagesQuery.status,
      isLoading,
      currentMessagesLength: messages.length,
      threadId,
      timestamp: Date.now()
    });
    
    console.log('📡 [useThreadData] 详细检查条件:', {
      hasMessagesQueryData: !!messagesQuery.data,
      messagesQueryData: messagesQuery.data,
      statusIsSuccess: messagesQuery.status === 'success',
      notLoading: !isLoading,
      willEnterIf: messagesQuery.data && messagesQuery.status === 'success' && !isLoading
    });
    
    if (messagesQuery.data && messagesQuery.status === 'success' && !isLoading) {
      // (debug logs removed)
      
      // Always reload messages when thread data changes or we have more raw messages than processed
      // 🎯 简化保护逻辑：主要依赖流式保护标志
      const shouldReload = messages.length === 0 || 
        (messagesQuery.data.length > messages.length + 50 && 
         !isStreamingOrRecentlyStreamedRef.current);
      
      console.log('🔄 [useThreadData] shouldReload检查:', {
        messagesLength: messages.length,
        queryDataLength: messagesQuery.data.length,
        isStreamingOrRecentlyStreamed: isStreamingOrRecentlyStreamedRef.current,
        agentStatus,
        condition1: messages.length === 0,
        condition2: messagesQuery.data.length > messages.length + 50,
        shouldReload
      });
      
      if (shouldReload) {
        // (debug logs removed)
        
        const unifiedMessages = (messagesQuery.data || [])
          .filter((msg) => msg.type !== 'status')
          .map((msg: ApiMessageType) => ({
            message_id: msg.message_id || null,
            thread_id: msg.thread_id || threadId,
            type: (msg.type || 'system') as UnifiedMessage['type'],
            is_llm_message: Boolean(msg.is_llm_message),
            content: msg.content || '',
            metadata: msg.metadata || '{}',
            created_at: msg.created_at || new Date().toISOString(),
            updated_at: msg.updated_at || new Date().toISOString(),
            agent_id: (msg as any).agent_id,
            agents: (msg as any).agents,
          }));

        // Merge strategy: preserve any local (optimistic/streamed) messages not in server yet
        setMessages((prev) => {
          const serverIds = new Set(
            unifiedMessages.map((m) => m.message_id).filter(Boolean) as string[],
          );
          
          // 🎯 增强保护：保护最近的流式消息（可能还没同步到服务器）
          const recentThreshold = Date.now() - 60000; // 1分钟内的消息
          const localExtras = (prev || []).filter(
            (m) =>
              !m.message_id ||
              (typeof m.message_id === 'string' && m.message_id.startsWith('temp-')) ||
              !serverIds.has(m.message_id as string) ||
              // 保护最近的流式助手消息，即使服务器已有ID
              (m.type === 'assistant' && 
               new Date(m.created_at).getTime() > recentThreshold &&
               !unifiedMessages.find(sm => sm.message_id === m.message_id && sm.content === m.content))
          );
          
                     console.log('🔄 [useThreadData] 消息合并详情:', {
             serverMessages: unifiedMessages.length,
             localExtras: localExtras.length,
             recentProtected: localExtras.filter(m => 
               m.type === 'assistant' && new Date(m.created_at).getTime() > recentThreshold
             ).length
           });
          
          const merged = [...unifiedMessages, ...localExtras].sort((a, b) => {
            const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
            return aTime - bTime;
          });
          
          // 🎯 深度比较：只有内容真正改变时才更新引用（基于测试页面成功经验）
          
          if (prev && prev.length === merged.length) {
            const hasChanges = prev.some((prevMsg, index) => {
              const mergedMsg = merged[index];
              return !mergedMsg || 
                     prevMsg.message_id !== mergedMsg.message_id ||
                     prevMsg.content !== mergedMsg.content ||
                     prevMsg.type !== mergedMsg.type ||
                     prevMsg.metadata !== mergedMsg.metadata;
            });
            

            
            if (!hasChanges) {
              console.log('✅ [useThreadData] Messages unchanged, reusing prev reference');
              return prev; // 🎯 返回相同引用，避免无限循环
            }
          }
          
          console.log('🔄 [useThreadData] setMessages called:', {
            prevLength: prev?.length || 0,
            unifiedMessagesLength: unifiedMessages.length,
            localExtrasLength: localExtras.length,
            mergedLength: merged.length,
            timestamp: Date.now()
          });
          
          // Messages set only from server merge; no cross-thread cache
          return merged;
        });
      } else {
        // (debug logs removed)
      }
    }
  }, [messagesQuery.data, messagesQuery.status, isLoading, threadId]); // [MESSAGE RELOAD LOOP] - 移除 messages.length 避免循环依赖

  return {
    messages,
    setMessages,
    project,
    sandboxId,
    projectName,
    agentRunId,
    setAgentRunId,
    agentStatus,
    setAgentStatus,
    isLoading,
    error,
    initialLoadCompleted: initialLoadCompleted.current,
    threadQuery,
    messagesQuery,
    projectQuery,
    agentRunsQuery,
  };
} 
