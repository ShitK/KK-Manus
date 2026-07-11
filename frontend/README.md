# KKManus Frontend

KKManus 的 Web 前端，负责对话、SSE 流式展示、工具结果卡片、GitHub 面试工作流和 Agent 运行评估。

## 技术栈

- Next.js App Router
- React
- TypeScript
- TanStack Query
- Tailwind CSS

## 本地启动

```bash
npm install
cp env.example .env.local
npm run dev -- -p 3001
```

默认后端地址为 `http://localhost:8000/api`，前端访问地址为 `http://localhost:3001`。根据本地环境修改 `.env.local`，不要提交真实凭据。

## 验证

```bash
npx tsc --noEmit
npm run build
```

GitHub 面试工作流的数据解析测试可以单独运行：

```bash
npx tsx --test src/components/thread/tool-views/github-repo-interview-workflow/_utils.test.ts
```

## 主要目录

```text
src/app/(dashboard)/agent-evals/                       Agent 运行评估工作台
src/components/thread/tool-views/                      工具结果展示
src/components/thread/tool-views/github-repo-interview-workflow/
src/hooks/react-query/                                 后端 API 查询封装
src/lib/api.ts                                         API 客户端
```

该前端基于 Suna / Kortix 风格的 Agent Web 应用继续改造，用户可见品牌统一为 KKManus，部分内部兼容标识仍保留。
