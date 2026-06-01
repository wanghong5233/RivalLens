import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Users, Activity, CheckCircle, AlertTriangle, Clock, Zap, Target, FileSearch, FileText, Shield } from "lucide-react";

import { useRunDetail, useDashboard } from "@/api/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface AgentInfo {
  name: string;
  role: string;
  status: "active" | "idle" | "busy" | "error";
  icon: React.ReactNode;
  description: string;
  responsibilities: string[];
  taskCount: number;
  successRate: number;
  avgLatencyMs: number;
}

export function AgentRolesPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const detailQuery = useRunDetail(runId);
  const dashboardQuery = useDashboard();

  const agents: AgentInfo[] = [
    {
      name: "信息采集 Agent",
      role: "Collector",
      status: "active",
      icon: <FileSearch className="h-6 w-6" />,
      description: "负责从公开渠道采集竞品相关信息，包括网页抓取、API获取、文档解析等",
      responsibilities: [
        "竞品官网数据采集",
        "用户评价抓取",
        "市场报告获取",
        "社交媒体监控",
        "问卷设计与调研",
        "用户访谈记录",
      ],
      taskCount: 156,
      successRate: 0.94,
      avgLatencyMs: 2340,
    },
    {
      name: "分析师 Agent",
      role: "Analyst",
      status: "busy",
      icon: <Target className="h-6 w-6" />,
      description: "负责对采集到的数据进行结构化整理和深度分析",
      responsibilities: [
        "功能特性识别",
        "定价模型分析",
        "用户画像构建",
        "SWOT分析",
        "市场定位评估",
        "趋势预测",
      ],
      taskCount: 89,
      successRate: 0.97,
      avgLatencyMs: 8560,
    },
    {
      name: "报告撰写 Agent",
      role: "Writer",
      status: "idle",
      icon: <FileText className="h-6 w-6" />,
      description: "负责将分析结果整理成结构化的竞品分析报告",
      responsibilities: [
        "报告大纲生成",
        "内容组织编排",
        "图表设计制作",
        "格式规范化",
        "报告导出",
        "报告版本管理",
      ],
      taskCount: 42,
      successRate: 0.99,
      avgLatencyMs: 15200,
    },
    {
      name: "质检 Agent",
      role: "QualityAssurance",
      status: "active",
      icon: <Shield className="h-6 w-6" />,
      description: "负责对分析结果进行质量校验和事实核查",
      responsibilities: [
        "证据完整性检查",
        "数据准确性验证",
        "逻辑一致性校验",
        "引用规范性检查",
        "问题识别与打回",
        "整改结果复核",
      ],
      taskCount: 178,
      successRate: 0.98,
      avgLatencyMs: 3120,
    },
  ];

  const statusConfig = {
    active: { label: "运行中", color: "bg-green-100 text-green-700", icon: <Activity className="h-4 w-4" /> },
    idle: { label: "空闲", color: "bg-slate-100 text-slate-600", icon: <Clock className="h-4 w-4" /> },
    busy: { label: "繁忙", color: "bg-yellow-100 text-yellow-700", icon: <Zap className="h-4 w-4" /> },
    error: { label: "异常", color: "bg-red-100 text-red-700", icon: <AlertTriangle className="h-4 w-4" /> },
  };

  const selectedAgentInfo = agents.find((a) => a.name === selectedAgent);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to={`/runs/${runId}`} className="flex items-center gap-2 text-slate-600 hover:text-slate-900">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回分析详情</span>
              </Link>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900">Agent 角色管理</h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-slate-500" />
              <span className="text-sm text-slate-600">{agents.length} 个 Agent</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading || dashboardQuery.isLoading ? (
          <div className="grid md:grid-cols-2 gap-4">
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ) : (
          <div className="grid lg:grid-cols-3 gap-6">
            {/* Agent List */}
            <div className="lg:col-span-1 space-y-3">
              {agents.map((agent) => (
                <Card
                  key={agent.name}
                  className={cn(
                    "border-0 shadow-md cursor-pointer transition-all hover:shadow-lg",
                    selectedAgent === agent.name && "border-2 border-blue-500 bg-blue-50",
                  )}
                  onClick={() => setSelectedAgent(selectedAgent === agent.name ? null : agent.name)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center text-blue-600">
                        {agent.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900 truncate">{agent.name}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full ${statusConfig[agent.status].color}`}>
                            {statusConfig[agent.status].icon}
                            {statusConfig[agent.status].label}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-4">
                      <div className="text-center">
                        <p className="text-lg font-semibold text-slate-900">{agent.taskCount}</p>
                        <p className="text-xs text-slate-500">任务数</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-semibold text-slate-900">{Math.round(agent.successRate * 100)}%</p>
                        <p className="text-xs text-slate-500">成功率</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-semibold text-slate-900">{(agent.avgLatencyMs / 1000).toFixed(1)}s</p>
                        <p className="text-xs text-slate-500">延迟</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Agent Detail */}
            <div className="lg:col-span-2">
              {selectedAgentInfo ? (
                <Card className="border-0 shadow-md">
                  <CardHeader className="pb-4">
                    <div className="flex items-center gap-3">
                      <div className="w-14 h-14 rounded-xl bg-blue-100 flex items-center justify-center text-blue-600">
                        {selectedAgentInfo.icon}
                      </div>
                      <div>
                        <CardTitle className="text-xl font-semibold text-slate-900">
                          {selectedAgentInfo.name}
                        </CardTitle>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-sm text-slate-500">角色标识: </span>
                          <code className="px-2 py-0.5 text-xs bg-slate-100 rounded">{selectedAgentInfo.role}</code>
                        </div>
                      </div>
                      <span className={`ml-auto inline-flex items-center gap-1 px-3 py-1.5 text-sm rounded-full ${statusConfig[selectedAgentInfo.status].color}`}>
                        {statusConfig[selectedAgentInfo.status].icon}
                        {statusConfig[selectedAgentInfo.status].label}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-2">职责描述</h4>
                      <p className="text-sm text-slate-600">{selectedAgentInfo.description}</p>
                    </div>

                    <div>
                      <h4 className="text-sm font-medium text-slate-700 mb-3">核心职责</h4>
                      <div className="grid sm:grid-cols-2 gap-2">
                        {selectedAgentInfo.responsibilities.map((item, index) => (
                          <div key={index} className="flex items-center gap-2 p-3 bg-slate-50 rounded-lg">
                            <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                            <span className="text-sm text-slate-700">{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid sm:grid-cols-3 gap-4">
                      <div className="p-4 bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl">
                        <p className="text-sm text-blue-600 mb-1">累计任务数</p>
                        <p className="text-2xl font-bold text-blue-900">{selectedAgentInfo.taskCount}</p>
                      </div>
                      <div className="p-4 bg-gradient-to-br from-green-50 to-green-100 rounded-xl">
                        <p className="text-sm text-green-600 mb-1">任务成功率</p>
                        <p className="text-2xl font-bold text-green-900">
                          {Math.round(selectedAgentInfo.successRate * 100)}%
                        </p>
                      </div>
                      <div className="p-4 bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl">
                        <p className="text-sm text-purple-600 mb-1">平均延迟</p>
                        <p className="text-2xl font-bold text-purple-900">
                          {(selectedAgentInfo.avgLatencyMs / 1000).toFixed(1)}s
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card className="border-0 shadow-md bg-slate-50/50">
                  <CardContent className="pt-16 pb-16 text-center">
                    <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-100 flex items-center justify-center">
                      <Users className="h-8 w-8 text-slate-400" />
                    </div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-2">选择一个 Agent</h3>
                    <p className="text-slate-500 text-sm">从左侧列表选择一个 Agent 查看详细信息</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* Error State */}
        {detailQuery.isError || dashboardQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">数据读取失败</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {detailQuery.error?.message ?? dashboardQuery.error?.message ?? "unknown error"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100 mt-auto">
        <div className="max-w-6xl mx-auto text-center">
          <p className="text-sm text-slate-500">
            RivalLens - AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}