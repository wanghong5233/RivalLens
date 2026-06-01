import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, X, TrendingUp, TrendingDown, Minus, Target, Zap, Shield, Award } from "lucide-react";

import { useRunDetail, useRunReport } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface CompetitorData {
  name: string;
  logo: string;
  overallScore: number;
  features: Record<string, boolean>;
  pricing: string;
  swot: {
    strengths: string[];
    weaknesses: string[];
    opportunities: string[];
    threats: string[];
  };
  marketPosition: {
    marketShare: number;
    growthRate: number;
    customerSatisfaction: number;
  };
}

export function CompetitorComparePage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [selectedCompetitors, setSelectedCompetitors] = useState<string[]>(["竞品A", "竞品B", "竞品C"]);

  const detailQuery = useRunDetail(runId);
  const reportQuery = useRunReport(runId);

  const allCompetitors: CompetitorData[] = [
    {
      name: "竞品A",
      logo: "A",
      overallScore: 85,
      pricing: "¥299/月",
      features: {
        "数据采集": true,
        "智能分析": true,
        "报告生成": true,
        "可视化": true,
        "API访问": true,
        "团队协作": true,
        "移动端": false,
        "私有化部署": false,
      },
      swot: {
        strengths: ["功能全面", "用户体验好", "技术领先"],
        weaknesses: ["价格偏高", "移动端缺失"],
        opportunities: ["企业市场拓展", "AI能力增强"],
        threats: ["竞争加剧", "用户流失风险"],
      },
      marketPosition: {
        marketShare: 35,
        growthRate: 12,
        customerSatisfaction: 88,
      },
    },
    {
      name: "竞品B",
      logo: "B",
      overallScore: 78,
      pricing: "¥199/月",
      features: {
        "数据采集": true,
        "智能分析": true,
        "报告生成": true,
        "可视化": false,
        "API访问": true,
        "团队协作": false,
        "移动端": true,
        "私有化部署": false,
      },
      swot: {
        strengths: ["价格实惠", "移动端体验好", "响应迅速"],
        weaknesses: ["功能不够完善", "团队协作能力弱"],
        opportunities: ["下沉市场", "功能补齐"],
        threats: ["高端市场竞争", "同质化严重"],
      },
      marketPosition: {
        marketShare: 25,
        growthRate: 18,
        customerSatisfaction: 82,
      },
    },
    {
      name: "竞品C",
      logo: "C",
      overallScore: 92,
      pricing: "定制报价",
      features: {
        "数据采集": true,
        "智能分析": true,
        "报告生成": true,
        "可视化": true,
        "API访问": true,
        "团队协作": true,
        "移动端": true,
        "私有化部署": true,
      },
      swot: {
        strengths: ["功能最全面", "企业级服务", "安全合规"],
        weaknesses: ["价格昂贵", "部署复杂"],
        opportunities: ["大型企业市场", "国际化"],
        threats: ["成本压力", "敏捷性不足"],
      },
      marketPosition: {
        marketShare: 20,
        growthRate: 8,
        customerSatisfaction: 95,
      },
    },
    {
      name: "竞品D",
      logo: "D",
      overallScore: 65,
      pricing: "¥99/月",
      features: {
        "数据采集": true,
        "智能分析": false,
        "报告生成": true,
        "可视化": false,
        "API访问": false,
        "团队协作": false,
        "移动端": true,
        "私有化部署": false,
      },
      swot: {
        strengths: ["价格最低", "上手简单", "轻量化"],
        weaknesses: ["功能有限", "数据分析能力弱"],
        opportunities: ["小微客户", "快速扩张"],
        threats: ["功能受限", "升级困难"],
      },
      marketPosition: {
        marketShare: 20,
        growthRate: 25,
        customerSatisfaction: 75,
      },
    },
  ];

  const featureList = ["数据采集", "智能分析", "报告生成", "可视化", "API访问", "团队协作", "移动端", "私有化部署"];

  const selectedData = allCompetitors.filter((c) => selectedCompetitors.includes(c.name));

  function toggleCompetitor(name: string): void {
    if (selectedCompetitors.includes(name)) {
      if (selectedCompetitors.length > 1) {
        setSelectedCompetitors(selectedCompetitors.filter((n) => n !== name));
      }
    } else {
      if (selectedCompetitors.length < 4) {
        setSelectedCompetitors([...selectedCompetitors, name]);
      }
    }
  }

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
                <h1 className="text-lg font-semibold text-slate-900">竞品对比分析</h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading || reportQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ) : (
          <>
            {/* Competitor Selection */}
            <Card className="border-0 shadow-md mb-6">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900">选择对比竞品</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {allCompetitors.map((competitor) => (
                    <Button
                      key={competitor.name}
                      variant={selectedCompetitors.includes(competitor.name) ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleCompetitor(competitor.name)}
                      className={cn(
                        "gap-2",
                        selectedCompetitors.includes(competitor.name)
                          ? "bg-blue-600 hover:bg-blue-700"
                          : "border-slate-300",
                      )}
                    >
                      <span className="w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-sm font-bold">
                        {competitor.logo}
                      </span>
                      {competitor.name}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Overview Cards */}
            <div className="grid gap-4 md:grid-cols-4 mb-6">
              {selectedData.map((competitor) => (
                <Card key={competitor.name} className="border-0 shadow-md">
                  <CardContent className="p-4">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-xl font-bold">
                        {competitor.logo}
                      </div>
                      <div>
                        <p className="font-semibold text-slate-900">{competitor.name}</p>
                        <p className="text-xs text-slate-500">{competitor.pricing}</p>
                      </div>
                    </div>
                    <div className="text-center">
                      <p className="text-4xl font-bold text-blue-600">{competitor.overallScore}</p>
                      <p className="text-xs text-slate-500 mt-1">综合评分</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Feature Comparison Table */}
            <Card className="border-0 shadow-md mb-6">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Zap className="h-5 w-5" />
                  功能对比
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="text-left py-3 px-4 text-sm font-medium text-slate-700">功能特性</th>
                        {selectedData.map((competitor) => (
                          <th key={competitor.name} className="text-center py-3 px-4 text-sm font-medium text-slate-700">
                            {competitor.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {featureList.map((feature) => (
                        <tr key={feature} className="border-b border-slate-100">
                          <td className="py-3 px-4 text-sm text-slate-700">{feature}</td>
                          {selectedData.map((competitor) => (
                            <td key={competitor.name} className="py-3 px-4 text-center">
                              {competitor.features[feature] ? (
                                <Check className="h-5 w-5 text-green-600 mx-auto" />
                              ) : (
                                <X className="h-5 w-5 text-red-400 mx-auto" />
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Market Position */}
            <Card className="border-0 shadow-md mb-6">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Target className="h-5 w-5" />
                  市场定位
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-3 gap-6">
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-4">市场份额</h4>
                    <div className="space-y-3">
                      {selectedData.map((competitor) => (
                        <div key={competitor.name}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-slate-600">{competitor.name}</span>
                            <span className="text-sm font-medium text-slate-900">{competitor.marketPosition.marketShare}%</span>
                          </div>
                          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full transition-all"
                              style={{ width: `${competitor.marketPosition.marketShare}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-4">增长率</h4>
                    <div className="space-y-3">
                      {selectedData.map((competitor) => (
                        <div key={competitor.name} className="flex items-center gap-3">
                          <span className="text-sm text-slate-600 w-16">{competitor.name}</span>
                          <div className={cn("flex items-center gap-1", competitor.marketPosition.growthRate >= 10 ? "text-green-600" : "text-blue-600")}>
                            {competitor.marketPosition.growthRate >= 10 ? (
                              <TrendingUp className="h-4 w-4" />
                            ) : (
                              <TrendingDown className="h-4 w-4" />
                            )}
                            <span className="text-sm font-medium">+{competitor.marketPosition.growthRate}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-4">用户满意度</h4>
                    <div className="space-y-3">
                      {selectedData.map((competitor) => (
                        <div key={competitor.name}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-slate-600">{competitor.name}</span>
                            <span className="text-sm font-medium text-slate-900">{competitor.marketPosition.customerSatisfaction}%</span>
                          </div>
                          <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all",
                                competitor.marketPosition.customerSatisfaction >= 90
                                  ? "bg-green-500"
                                  : competitor.marketPosition.customerSatisfaction >= 80
                                  ? "bg-blue-500"
                                  : "bg-yellow-500",
                              )}
                              style={{ width: `${competitor.marketPosition.customerSatisfaction}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* SWOT Analysis */}
            <Card className="border-0 shadow-md">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Shield className="h-5 w-5" />
                  SWOT 分析
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4">
                  {selectedData.map((competitor) => (
                    <div key={competitor.name} className="border border-slate-200 rounded-xl overflow-hidden">
                      <div className="bg-slate-50 px-4 py-2 border-b border-slate-200">
                        <div className="flex items-center gap-2">
                          <span className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600 font-bold">
                            {competitor.logo}
                          </span>
                          <span className="font-medium text-slate-900">{competitor.name}</span>
                        </div>
                      </div>
                      <div className="grid grid-cols-2">
                        <div className="p-4 bg-green-50/50">
                          <h4 className="text-sm font-medium text-green-700 mb-2 flex items-center gap-1">
                            <Award className="h-4 w-4" />
                            优势
                          </h4>
                          <ul className="space-y-1">
                            {competitor.swot.strengths.map((item, index) => (
                              <li key={index} className="text-sm text-green-800 flex items-center gap-2">
                                <Minus className="h-3 w-3" />
                                {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="p-4 bg-red-50/50">
                          <h4 className="text-sm font-medium text-red-700 mb-2">劣势</h4>
                          <ul className="space-y-1">
                            {competitor.swot.weaknesses.map((item, index) => (
                              <li key={index} className="text-sm text-red-800 flex items-center gap-2">
                                <Minus className="h-3 w-3" />
                                {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="p-4 bg-blue-50/50">
                          <h4 className="text-sm font-medium text-blue-700 mb-2">机会</h4>
                          <ul className="space-y-1">
                            {competitor.swot.opportunities.map((item, index) => (
                              <li key={index} className="text-sm text-blue-800 flex items-center gap-2">
                                <Minus className="h-3 w-3" />
                                {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="p-4 bg-yellow-50/50">
                          <h4 className="text-sm font-medium text-yellow-700 mb-2">威胁</h4>
                          <ul className="space-y-1">
                            {competitor.swot.threats.map((item, index) => (
                              <li key={index} className="text-sm text-yellow-800 flex items-center gap-2">
                                <Minus className="h-3 w-3" />
                                {item}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
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