import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, Users, Plus, Search, Filter, ChevronDown, ChevronUp, Download, Trash2, Edit3 } from "lucide-react";

import { useRunDetail } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface SurveyTemplate {
  id: string;
  name: string;
  description: string;
  questions: number;
  category: string;
  created_at: string;
  usage_count: number;
}

interface InterviewRecord {
  id: string;
  interviewee: string;
  role: string;
  date: string;
  duration: string;
  status: "completed" | "pending" | "in_progress";
  questions: string[];
  answers: string[];
}

export function SurveyPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [activeTab, setActiveTab] = useState<"templates" | "interviews">("templates");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedInterview, setExpandedInterview] = useState<string | null>(null);

  const detailQuery = useRunDetail(runId);

  const mockTemplates: SurveyTemplate[] = [
    {
      id: "temp-001",
      name: "竞品功能评估问卷",
      description: "用于收集用户对竞品功能的评价和反馈",
      questions: 12,
      category: "功能分析",
      created_at: "2024-01-10",
      usage_count: 45,
    },
    {
      id: "temp-002",
      name: "用户满意度调研",
      description: "评估用户对竞品产品的整体满意度",
      questions: 8,
      category: "用户研究",
      created_at: "2024-01-15",
      usage_count: 23,
    },
    {
      id: "temp-003",
      name: "定价敏感度测试",
      description: "了解用户对竞品定价的接受程度",
      questions: 6,
      category: "市场分析",
      created_at: "2024-01-18",
      usage_count: 18,
    },
    {
      id: "temp-004",
      name: "产品推荐度调查",
      description: "NPS调查，了解用户推荐意愿",
      questions: 5,
      category: "用户研究",
      created_at: "2024-01-20",
      usage_count: 32,
    },
  ];

  const mockInterviews: InterviewRecord[] = [
    {
      id: "int-001",
      interviewee: "张产品",
      role: "产品经理",
      date: "2024-01-22 14:00",
      duration: "30分钟",
      status: "completed",
      questions: ["您如何评价竞品A的用户界面？", "竞品B的哪些功能最吸引您？", "您愿意为这类产品支付多少费用？"],
      answers: ["竞品A的界面设计简洁现代，用户体验很好，特别是数据可视化部分做得很棒。", "竞品B的团队协作功能和移动端体验是我最看重的，这两个点做得很出色。", "根据功能完整性，我认为每月200-300元是合理的价格区间。"],
    },
    {
      id: "int-002",
      interviewee: "李分析",
      role: "市场分析师",
      date: "2024-01-23 10:00",
      duration: "45分钟",
      status: "completed",
      questions: ["竞品C在市场中的定位如何？", "您认为竞品的主要优势是什么？", "市场上还有哪些潜在的竞争威胁？"],
      answers: ["竞品C主要面向大型企业客户，定位高端市场，提供私有化部署方案。", "竞品C的主要优势在于其强大的数据安全保障和完善的企业级服务支持。", "新兴的AI驱动产品可能会对现有竞品造成威胁，需要关注技术发展趋势。"],
    },
    {
      id: "int-003",
      interviewee: "王运营",
      role: "运营总监",
      date: "2024-01-25 15:30",
      duration: "25分钟",
      status: "pending",
      questions: [],
      answers: [],
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to={`/runs/${runId}`} className="flex items-center gap-2 text-slate-600 hover:text-slate-900">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回分析详情</span>
              </Link>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900">用户研究管理</h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              新建调研
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        ) : (
          <>
            {/* Tab Navigation */}
            <div className="flex gap-2 mb-6">
              <Button
                variant={activeTab === "templates" ? "default" : "outline"}
                size="sm"
                onClick={() => setActiveTab("templates")}
                className={cn(
                  "gap-2",
                  activeTab === "templates" ? "bg-blue-600 hover:bg-blue-700" : "border-slate-300",
                )}
              >
                <FileText className="h-4 w-4" />
                问卷模板
              </Button>
              <Button
                variant={activeTab === "interviews" ? "default" : "outline"}
                size="sm"
                onClick={() => setActiveTab("interviews")}
                className={cn(
                  "gap-2",
                  activeTab === "interviews" ? "bg-blue-600 hover:bg-blue-700" : "border-slate-300",
                )}
              >
                <Users className="h-4 w-4" />
                访谈记录
              </Button>
            </div>

            {/* Templates Tab */}
            {activeTab === "templates" && (
              <>
                {/* Search & Filter */}
                <Card className="border-0 shadow-md mb-6">
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-center gap-4">
                      <div className="flex-1 min-w-[200px] relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                        <input
                          type="text"
                          placeholder="搜索问卷模板..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="w-full pl-10 pr-4 py-2 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
                        />
                      </div>
                      <Button variant="outline" size="sm" className="gap-2 border-slate-300">
                        <Filter className="h-4 w-4" />
                        筛选
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Templates List */}
                <div className="grid gap-4 md:grid-cols-2">
                  {mockTemplates.map((template) => (
                    <Card key={template.id} className="border-0 shadow-md hover:shadow-lg transition-all">
                      <CardHeader className="pb-3">
                        <div className="flex items-start justify-between">
                          <div>
                            <CardTitle className="text-base font-semibold text-slate-900">{template.name}</CardTitle>
                            <p className="text-sm text-slate-500 mt-1">{template.description}</p>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                              <Edit3 className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-red-500 hover:text-red-600">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div className="flex flex-wrap items-center gap-4 text-sm">
                          <div className="flex items-center gap-1.5">
                            <FileText className="h-4 w-4 text-slate-400" />
                            <span className="text-slate-600">{template.questions} 个问题</span>
                          </div>
                          <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">
                            {template.category}
                          </span>
                        </div>
                        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                          <span className="text-xs text-slate-500">创建于 {template.created_at}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-slate-500">使用 {template.usage_count} 次</span>
                            <Button variant="outline" size="sm" className="gap-2 border-slate-300">
                              <Download className="h-4 w-4" />
                              使用模板
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </>
            )}

            {/* Interviews Tab */}
            {activeTab === "interviews" && (
              <div className="space-y-4">
                {mockInterviews.map((interview) => (
                  <Card key={interview.id} className="border-0 shadow-md">
                    <CardHeader className="pb-3 cursor-pointer" onClick={() => setExpandedInterview(expandedInterview === interview.id ? null : interview.id)}>
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="text-base font-semibold text-slate-900">{interview.interviewee}</CardTitle>
                          <div className="flex flex-wrap items-center gap-4 mt-2 text-sm">
                            <span className="text-slate-500">{interview.role}</span>
                            <span className="text-slate-500">{interview.date}</span>
                            <span className="text-slate-500">时长: {interview.duration}</span>
                            <span className={cn(
                              "px-2 py-0.5 text-xs rounded-full",
                              interview.status === "completed" ? "bg-green-100 text-green-700" :
                              interview.status === "in_progress" ? "bg-blue-100 text-blue-700" :
                              "bg-slate-100 text-slate-600",
                            )}>
                              {interview.status === "completed" ? "已完成" :
                               interview.status === "in_progress" ? "进行中" : "待安排"}
                            </span>
                          </div>
                        </div>
                        {expandedInterview === interview.id ? (
                          <ChevronUp className="h-5 w-5 text-slate-400" />
                        ) : (
                          <ChevronDown className="h-5 w-5 text-slate-400" />
                        )}
                      </div>
                    </CardHeader>
                    {expandedInterview === interview.id && (
                      <CardContent className="space-y-4">
                        {interview.status === "completed" ? (
                          <div className="space-y-4">
                            {interview.questions.map((question, index) => (
                              <div key={index} className="p-4 bg-slate-50 rounded-xl">
                                <p className="text-sm font-medium text-slate-700 mb-2">Q: {question}</p>
                                <p className="text-sm text-slate-600">A: {interview.answers[index]}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-6 bg-amber-50 rounded-xl text-center">
                            <p className="text-sm text-amber-700">
                              {interview.status === "pending" ? "访谈尚未进行，等待安排" : "访谈进行中"}
                            </p>
                          </div>
                        )}
                      </CardContent>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
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