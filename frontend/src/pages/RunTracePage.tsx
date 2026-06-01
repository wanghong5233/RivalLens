import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Activity, Code2, GitBranch, Cpu } from "lucide-react";

import { useRunTrace } from "@/api/hooks";
import { useRunEvents } from "@/api/sse";
import { RunTraceDag } from "@/components/dag/RunTraceDag";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { buildEvidenceLinkFromToolArgs } from "@/lib/evidenceLinks";
import { formatDateTime } from "@/lib/format";

export function RunTracePage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  useRunEvents(runId);
  const traceQuery = useRunTrace(runId);

  const llmSummaries = useMemo(() => {
    if (!traceQuery.data) {
      return [];
    }
    return traceQuery.data.steps
      .map((step) => {
        const payload = step.payload;
        const knownKeys = [
          "analysis_mode",
          "qa_semantic_mode",
          "react_turn_count",
          "compression_count",
          "template_id",
        ];
        const highlights = knownKeys
          .filter((key) => key in payload)
          .map((key) => `${key}=${String(payload[key])}`);
        if (highlights.length === 0) {
          return null;
        }
        return {
          stepId: step.step_id,
          agentName: step.agent_name,
          createdAt: step.created_at,
          highlights,
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
  }, [traceQuery.data]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-900/80 backdrop-blur-sm border-b border-slate-700">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to={`/runs/${runId}`} className="flex items-center gap-2 text-slate-400 hover:text-white">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回分析详情</span>
              </Link>
              <div className="h-4 w-px bg-slate-700" />
              <div>
                <h1 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Code2 className="h-5 w-5" />
                  开发者视图
                </h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Loading State */}
        {traceQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-32 w-full bg-slate-700 rounded-xl" />
            <Skeleton className="h-48 w-full bg-slate-700 rounded-xl" />
          </div>
        ) : null}

        {/* Error State */}
        {traceQuery.isError ? (
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <Activity className="h-6 w-6 text-red-500 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-red-400">获取 Trace 失败</p>
                  <p className="text-xs text-red-600 mt-1">{traceQuery.error.message}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Trace Content */}
        {traceQuery.data ? (
          <Tabs defaultValue="dag" className="w-full">
            <div className="flex justify-center mb-6">
              <TabsList className="bg-slate-800 border border-slate-700 p-1">
                <TabsTrigger value="dag" className="data-[state=active]:bg-slate-700">
                  <GitBranch className="h-4 w-4 mr-2" />
                  DAG
                </TabsTrigger>
                <TabsTrigger value="steps" className="data-[state=active]:bg-slate-700">
                  <Activity className="h-4 w-4 mr-2" />
                  Steps
                </TabsTrigger>
                <TabsTrigger value="decisions" className="data-[state=active]:bg-slate-700">
                  <Cpu className="h-4 w-4 mr-2" />
                  Supervisor decisions
                </TabsTrigger>
                <TabsTrigger value="llm" className="data-[state=active]:bg-slate-700">
                  <Code2 className="h-4 w-4 mr-2" />
                  LLM calls
                </TabsTrigger>
              </TabsList>
            </div>

            <Card className="bg-slate-800/50 border-slate-700">
              <TabsContent value="dag">
                <CardHeader className="border-b border-slate-700">
                  <CardTitle className="text-base text-white">DAG 决策回放</CardTitle>
                </CardHeader>
                <CardContent>
                  <RunTraceDag trace={traceQuery.data} />
                </CardContent>
              </TabsContent>

              <TabsContent value="steps">
                <CardHeader className="border-b border-slate-700">
                  <CardTitle className="text-base text-white">Steps</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {traceQuery.data.steps.map((step) => (
                    <div 
                      key={step.step_id} 
                      className="rounded-lg border border-slate-700 bg-slate-800/50 p-4"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm text-white">
                            <span className="text-slate-400">[{formatDateTime(step.created_at)}]</span> 
                            {step.agent_name} · {step.status}
                          </p>
                          <p className="text-xs text-slate-500 mt-1">{step.step_id}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </TabsContent>

              <TabsContent value="decisions">
                <CardHeader className="border-b border-slate-700">
                  <CardTitle className="text-base text-white">Supervisor decisions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {traceQuery.data.supervisor_decisions.map((decision) => {
                    const evidenceLink = buildEvidenceLinkFromToolArgs(runId, decision.tool_args);
                    return (
                      <div 
                        key={decision.id} 
                        className="rounded-lg border border-slate-700 bg-slate-800/50 p-4"
                      >
                        <p className="text-sm text-white">
                          <span className="text-slate-400">[{formatDateTime(decision.created_at)}]</span> 
                          iter={decision.iteration} · {decision.chosen_tool}
                        </p>
                        <p className="mt-2 text-xs text-slate-400">{decision.reasoning_summary}</p>
                        {evidenceLink !== null ? (
                          <Link 
                            className="mt-3 inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-all" 
                            to={evidenceLink}
                          >
                            <Activity className="h-3 w-3" />
                            查看相关证据
                          </Link>
                        ) : null}
                      </div>
                    );
                  })}
                </CardContent>
              </TabsContent>

              <TabsContent value="llm">
                <CardHeader className="border-b border-slate-700">
                  <CardTitle className="text-base text-white">LLM highlights (from step payload)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {llmSummaries.length === 0 ? (
                    <div className="text-center py-8">
                      <Code2 className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-sm text-slate-500">暂无可解析的 LLM 摘要字段。</p>
                    </div>
                  ) : (
                    llmSummaries.map((item) => (
                      <div 
                        key={item.stepId} 
                        className="rounded-lg border border-slate-700 bg-slate-800/50 p-4"
                      >
                        <p className="text-sm text-white">
                          <span className="text-slate-400">[{formatDateTime(item.createdAt)}]</span> 
                          {item.agentName}
                        </p>
                        <p className="mt-2 text-xs text-slate-400">{item.highlights.join(" · ")}</p>
                      </div>
                    ))
                  )}
                </CardContent>
              </TabsContent>
            </Card>
          </Tabs>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-slate-900 border-t border-slate-700 mt-auto">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-sm text-slate-600">
            RivalLens - AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}
