import { useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, Clock, FileText, Link2, AlertCircle, Shield, ChevronRight, Database, Sparkles, Eye, Zap } from "lucide-react";

import { useRunDetail, useRunEvidence } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

interface TraceStep {
  step: string;
  agent: string;
  timestamp: string;
  action: string;
  status: "success" | "pending" | "error";
  icon: React.ReactNode;
}

export function EvidenceDetailPage(): JSX.Element {
  const { runId: runIdFromParams, evidenceId: evidenceIdFromParams } = useParams<{
    runId: string;
    evidenceId: string;
  }>();
  const runId = runIdFromParams ?? "";
  const evidenceId = evidenceIdFromParams ?? "";

  const detailQuery = useRunDetail(runId);
  const evidenceQuery = useRunEvidence(runId);

  const currentEvidence = evidenceQuery.data?.find((item) => item.evidence_id === evidenceId);

  const mockAnalysisConclusions = [
    {
      id: "c1",
      text: "竞品X在用户界面设计方面注重简洁性，采用了现代化的卡片式布局",
      confidence: 0.92,
      relatedFeatures: ["UI设计", "用户体验"],
    },
    {
      id: "c2",
      text: "根据用户评价数据，竞品X的移动端体验评分较高",
      confidence: 0.87,
      relatedFeatures: ["移动端", "用户评价"],
    },
    {
      id: "c3",
      text: "竞品X的定价策略偏向中高端市场",
      confidence: 0.78,
      relatedFeatures: ["定价策略", "市场定位"],
    },
  ];

  const mockTraceChain: TraceStep[] = [
    {
      step: "数据采集",
      agent: "信息采集 Agent",
      timestamp: "2024-01-15 10:30:00",
      action: "从官方网站抓取产品页面",
      status: "success",
      icon: <Zap className="h-4 w-4" />,
    },
    {
      step: "数据清洗",
      agent: "信息采集 Agent",
      timestamp: "2024-01-15 10:31:00",
      action: "去除HTML标签，提取纯文本内容",
      status: "success",
      icon: <Sparkles className="h-4 w-4" />,
    },
    {
      step: "内容提取",
      agent: "分析师 Agent",
      timestamp: "2024-01-15 10:35:00",
      action: "识别关键信息：功能特性、定价信息",
      status: "success",
      icon: <Eye className="h-4 w-4" />,
    },
    {
      step: "质量校验",
      agent: "质检 Agent",
      timestamp: "2024-01-15 10:38:00",
      action: "验证数据完整性和准确性",
      status: "success",
      icon: <Shield className="h-4 w-4" />,
    },
    {
      step: "入库存储",
      agent: "系统",
      timestamp: "2024-01-15 10:40:00",
      action: "存储到知识库，生成证据ID",
      status: "success",
      icon: <Database className="h-4 w-4" />,
    },
  ];

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return "from-green-500 to-emerald-600";
    if (confidence >= 0.7) return "from-yellow-500 to-orange-600";
    return "from-red-500 to-rose-600";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="sm"
                className="gap-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 -ml-2"
                onClick={() => window.history.back()}
              >
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回</span>
              </Button>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900">证据详情</h1>
                <p className="text-xs text-slate-500 font-mono">{evidenceId}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading || evidenceQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ) : currentEvidence ? (
          <div className="space-y-6">
            {/* Evidence Basic Info */}
            <Card className="border-0 shadow-md overflow-hidden">
              <CardHeader className="pb-4 bg-gradient-to-r from-blue-50 to-purple-50/30 -mx-4 -mt-4 px-6 py-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      基础信息
                    </CardTitle>
                    <div className="flex flex-wrap items-center gap-4 mt-3 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatDateTime(currentEvidence.collected_at)}
                      </span>
                      <span className="px-2 py-1 bg-slate-200 text-slate-600 rounded-full">
                        {currentEvidence.source_type}
                      </span>
                      {currentEvidence.competitor_id && (
                        <span className="px-2 py-1 bg-blue-100 text-blue-600 rounded-full">
                          {currentEvidence.competitor_id}
                        </span>
                      )}
                    </div>
                  </div>
                  {currentEvidence.source_url && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-2 border-slate-300 transition-all hover-lift"
                      onClick={() => window.open(currentEvidence.source_url || undefined, "_blank")}
                    >
                      <ExternalLink className="h-4 w-4" />
                      打开原页面
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {currentEvidence.source_title && (
                  <div className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50/50 rounded-xl border border-blue-100">
                    <p className="text-sm font-medium text-blue-600 mb-1">来源标题</p>
                    <p className="text-slate-900 font-medium">{currentEvidence.source_title}</p>
                  </div>
                )}
                <div className="p-4 bg-slate-50 rounded-xl">
                  <p className="text-sm font-medium text-slate-500 mb-2">内容摘要</p>
                  <div className="text-sm text-slate-700 whitespace-pre-wrap leading-6 max-h-64 overflow-y-auto pr-2">
                    {currentEvidence.sanitized_text}
                  </div>
                </div>
                {currentEvidence.source_url && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Link2 className="h-3 w-3" />
                    <a
                      href={currentEvidence.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:text-blue-700 hover:underline truncate max-w-md"
                    >
                      {currentEvidence.source_url}
                    </a>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Trace Chain Visualization */}
            <Card className="border-0 shadow-md overflow-hidden">
              <CardHeader className="pb-3 bg-gradient-to-r from-purple-50 to-pink-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Link2 className="h-5 w-5" />
                  溯源链路
                </CardTitle>
                <p className="text-sm text-slate-500">证据从采集到入库的完整流程</p>
              </CardHeader>
              <CardContent>
                {/* Progress Bar */}
                <div className="mb-6">
                  <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                    <span>处理进度</span>
                    <span className="text-green-600 font-medium">已完成</span>
                  </div>
                  <div className="relative h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 via-purple-500 to-green-500 rounded-full w-full animate-pulse" />
                  </div>
                </div>

                {/* Flow Visualization */}
                <div className="relative">
                  {/* Vertical Line */}
                  <div className="absolute left-[22px] top-0 bottom-0 w-1 bg-gradient-to-b from-blue-500 via-purple-500 to-green-500 rounded-full">
                    <div className="absolute inset-0 bg-white animate-pulse opacity-30" />
                  </div>

                  {/* Steps */}
                  <div className="space-y-6">
                    {mockTraceChain.map((item, index) => (
                      <div
                        key={index}
                        className="relative flex items-start gap-4 group animate-in fade-in slide-in-from-left-2"
                        style={{ animationDelay: `${index * 150}ms` }}
                      >
                        {/* Circle */}
                        <div className="relative z-10">
                          <div
                            className={cn(
                              "w-11 h-11 rounded-full flex items-center justify-center transition-all duration-300",
                              item.status === "success"
                                ? "bg-gradient-to-br from-green-400 to-emerald-500 text-white shadow-lg shadow-green-500/30"
                                : item.status === "pending"
                                ? "bg-gradient-to-br from-yellow-400 to-orange-500 text-white shadow-lg"
                                : "bg-gradient-to-br from-red-400 to-rose-500 text-white shadow-lg",
                              "group-hover:scale-110",
                            )}
                          >
                            {item.icon}
                          </div>
                          {/* Glow effect */}
                          <div
                            className={cn(
                              "absolute inset-0 rounded-full animate-ping opacity-20",
                              item.status === "success" ? "bg-green-500" : item.status === "pending" ? "bg-yellow-500" : "bg-red-500",
                            )}
                          />
                        </div>

                        {/* Content */}
                        <div className="flex-1">
                          <div
                            className="bg-white border border-slate-100 rounded-xl p-4 transition-all duration-300 hover:border-blue-200 hover:shadow-md hover:-translate-y-0.5"
                          >
                            <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                              <div className="flex items-center gap-2">
                                <h4 className="font-semibold text-slate-900">{item.step}</h4>
                                <span
                                  className={cn(
                                    "px-2 py-0.5 text-xs rounded-full",
                                    item.status === "success" ? "bg-green-100 text-green-700" : item.status === "pending" ? "bg-yellow-100 text-yellow-700" : "bg-red-100 text-red-700",
                                  )}
                                >
                                  {item.status === "success" ? "完成" : item.status === "pending" ? "进行中" : "失败"}
                                </span>
                              </div>
                              <span className="text-xs text-slate-400">{item.timestamp}</span>
                            </div>
                            <p className="text-sm text-slate-600 mb-2">{item.action}</p>
                            <div className="flex items-center gap-2">
                              <span className="inline-block px-2 py-0.5 text-xs bg-blue-100 text-blue-600 rounded">
                                {item.agent}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Arrow indicator */}
                        {index < mockTraceChain.length - 1 && (
                          <ChevronRight className="absolute left-[18px] -bottom-4 h-4 w-4 text-slate-400 transform rotate-90" />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Related Analysis */}
            <Card className="border-0 shadow-md overflow-hidden">
              <CardHeader className="pb-3 bg-gradient-to-r from-emerald-50 to-teal-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  关联分析结论
                </CardTitle>
                <p className="text-sm text-slate-500">基于此证据得出的分析结论</p>
              </CardHeader>
              <CardContent className="space-y-4">
                {mockAnalysisConclusions.map((conclusion, index) => (
                  <div
                    key={conclusion.id}
                    className="bg-white border border-slate-100 rounded-xl p-4 transition-all duration-300 hover:border-blue-200 hover:shadow-md hover:-translate-y-0.5 animate-in fade-in slide-in-from-right-2"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex items-start gap-4">
                      {/* Confidence Badge */}
                      <div className="relative">
                        <div
                          className={cn(
                            "w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold text-white",
                            `bg-gradient-to-br ${getConfidenceColor(conclusion.confidence)}`,
                          )}
                        >
                          {Math.round(conclusion.confidence * 100)}%
                        </div>
                        {/* Confidence ring */}
                        <svg className="absolute inset-0 w-10 h-10 -rotate-90">
                          <circle
                            cx="20"
                            cy="20"
                            r="18"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            className={cn(
                              "opacity-20",
                              conclusion.confidence >= 0.9 ? "text-green-500" : conclusion.confidence >= 0.7 ? "text-yellow-500" : "text-red-500",
                            )}
                          />
                          <circle
                            cx="20"
                            cy="20"
                            r="18"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeDasharray={`${conclusion.confidence * 113} 113`}
                            className={cn(
                              conclusion.confidence >= 0.9 ? "text-green-500" : conclusion.confidence >= 0.7 ? "text-yellow-500" : "text-red-500",
                            )}
                          />
                        </svg>
                      </div>

                      {/* Content */}
                      <div className="flex-1">
                        <p className="text-sm text-slate-700 leading-relaxed mb-3">{conclusion.text}</p>
                        <div className="flex flex-wrap gap-2">
                          {conclusion.relatedFeatures.map((feature) => (
                            <span
                              key={feature}
                              className="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-full"
                            >
                              {feature}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Evidence Metadata */}
            <Card className="border-0 shadow-md">
              <CardContent className="p-4 bg-slate-50 rounded-xl">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  <div>
                    <p className="text-2xl font-bold text-blue-600">{mockTraceChain.length}</p>
                    <p className="text-xs text-slate-500 mt-1">处理步骤</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-green-600">100%</p>
                    <p className="text-xs text-slate-500 mt-1">成功率</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-purple-600">10分钟</p>
                    <p className="text-xs text-slate-500 mt-1">处理耗时</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-orange-600">{mockAnalysisConclusions.length}</p>
                    <p className="text-xs text-slate-500 mt-1">关联结论</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-8 text-center">
              <AlertCircle className="h-12 w-12 text-amber-600 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-amber-800 mb-2">证据未找到</h3>
              <p className="text-sm text-amber-600">当前证据 ID 不存在于本次分析中</p>
            </CardContent>
          </Card>
        )}

        {/* Error State */}
        {detailQuery.isError || evidenceQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">数据读取失败</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {detailQuery.error?.message ?? evidenceQuery.error?.message ?? "unknown error"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100 mt-auto">
        <div className="max-w-5xl mx-auto text-center">
          <p className="text-sm text-slate-500">
            RivalLens - AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}