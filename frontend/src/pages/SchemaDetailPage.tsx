import { useState, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronRight, DollarSign, Users, Layers, Check, X, AlertCircle, Search, Expand, ChevronDown } from "lucide-react";

import { useRunDetail, useRunReport } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface FeatureNode {
  name: string;
  description: string;
  available: boolean;
  children?: FeatureNode[];
}

interface PricingTier {
  name: string;
  price: string;
  features: string[];
  popular?: boolean;
}

interface UserProfile {
  segment: string;
  description: string;
  needs: string[];
  usage_patterns: string[];
}

export function SchemaDetailPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [activeTab, setActiveTab] = useState<"features" | "pricing" | "users">("features");
  const [expandedFeatures, setExpandedFeatures] = useState<Set<string>>(new Set(["root"]));
  const [searchQuery, setSearchQuery] = useState("");

  const detailQuery = useRunDetail(runId);
  const reportQuery = useRunReport(runId);

  const mockFeatureTree: FeatureNode = {
    name: "核心功能",
    description: "竞品的主要功能模块",
    available: true,
    children: [
      {
        name: "数据采集",
        description: "自动化数据收集能力",
        available: true,
        children: [
          { name: "网页抓取", description: "支持主流网站数据抓取", available: true },
          { name: "API集成", description: "对接第三方数据源", available: true },
          { name: "实时监控", description: "持续追踪竞品动态", available: false },
        ],
      },
      {
        name: "分析处理",
        description: "数据加工与分析能力",
        available: true,
        children: [
          { name: "自然语言处理", description: "文本分析与情感识别", available: true },
          { name: "可视化报表", description: "数据图表展示", available: true },
          { name: "趋势预测", description: "基于历史数据预测", available: false },
        ],
      },
      {
        name: "报告生成",
        description: "自动生成分析报告",
        available: true,
        children: [
          { name: "结构化报告", description: "标准化报告模板", available: true },
          { name: "自定义报告", description: "按需定制报告内容", available: true },
          { name: "报告导出", description: "多格式导出支持", available: true },
        ],
      },
    ],
  };

  const mockPricingTiers: PricingTier[] = [
    {
      name: "基础版",
      price: "¥99/月",
      features: ["最多5个竞品", "基础数据采集", "周报生成", "邮件告警"],
    },
    {
      name: "专业版",
      price: "¥299/月",
      features: ["最多20个竞品", "高级数据分析", "日报/周报", "API访问", "团队协作"],
      popular: true,
    },
    {
      name: "企业版",
      price: "定制报价",
      features: ["无限竞品", "私有化部署", "定制开发", "专属客服", "SLA保障"],
    },
  ];

  const mockUserProfiles: UserProfile[] = [
    {
      segment: "产品经理",
      description: "负责产品规划和竞品分析的专业人士",
      needs: ["竞品功能对比", "市场趋势分析", "用户评价洞察"],
      usage_patterns: ["每周生成竞品报告", "关注功能迭代动态", "定期SWOT分析"],
    },
    {
      segment: "市场分析师",
      description: "关注市场动态和竞争格局的分析师",
      needs: ["市场份额分析", "定价策略研究", "用户画像分析"],
      usage_patterns: ["月度市场报告", "竞品定价监控", "用户调研分析"],
    },
    {
      segment: "创业者",
      description: "早期创业公司创始人或核心成员",
      needs: ["低成本解决方案", "快速入门", "灵活配置"],
      usage_patterns: ["快速竞品扫描", "竞品功能对标", "融资材料准备"],
    },
  ];

  const featureStats = useMemo(() => {
    let total = 0;
    let available = 0;
    
    function count(node: FeatureNode) {
      total++;
      if (node.available) available++;
      node.children?.forEach(count);
    }
    
    count(mockFeatureTree);
    return { total, available, unavailable: total - available };
  }, []);

  function toggleFeature(featureId: string): void {
    const newExpanded = new Set(expandedFeatures);
    if (newExpanded.has(featureId)) {
      newExpanded.delete(featureId);
    } else {
      newExpanded.add(featureId);
    }
    setExpandedFeatures(newExpanded);
  }

  function expandAllFeatures(): void {
    const allIds = new Set<string>();
    
    function collectIds(node: FeatureNode, parentId: string) {
      const nodeId = `${parentId}-${node.name}`;
      allIds.add(nodeId);
      node.children?.forEach((child) => collectIds(child, nodeId));
    }
    
    collectIds(mockFeatureTree, "root");
    setExpandedFeatures(allIds);
  }

  function collapseAllFeatures(): void {
    setExpandedFeatures(new Set(["root"]));
  }

  function filterNode(node: FeatureNode, query: string): boolean {
    if (!query) return true;
    const q = query.toLowerCase();
    if (node.name.toLowerCase().includes(q) || node.description.toLowerCase().includes(q)) {
      return true;
    }
    return node.children?.some((child) => filterNode(child, query)) ?? false;
  }

  function renderFeatureNode(node: FeatureNode, depth: number = 0, parentId: string = "root"): JSX.Element | null {
    const nodeId = `${parentId}-${node.name}`;
    const isExpanded = expandedFeatures.has(nodeId);
    const hasChildren = node.children && node.children.length > 0;
    const matchesFilter = filterNode(node, searchQuery);
    
    if (!matchesFilter) return null;

    return (
      <div key={nodeId} className="relative animate-in fade-in slide-in-from-top-2 duration-300">
        <div
          className={cn(
            "flex items-center gap-3 py-3 px-4 rounded-lg cursor-pointer transition-all hover:bg-slate-50 hover-lift",
            depth > 0 && `ml-${depth * 6}`,
          )}
          onClick={() => hasChildren && toggleFeature(nodeId)}
        >
          <div className="flex-shrink-0">
            {hasChildren ? (
              <ChevronRight
                className={cn(
                  "h-4 w-4 text-slate-500 transition-transform duration-200",
                  isExpanded && "rotate-90",
                )}
              />
            ) : (
              <div className="w-4 h-4" />
            )}
          </div>
          <div className={cn("flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center transition-transform hover:scale-110", node.available ? "bg-green-100" : "bg-red-100")}>
            {node.available ? (
              <Check className="h-3 w-3 text-green-600" />
            ) : (
              <X className="h-3 w-3 text-red-600" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-slate-900 truncate">{node.name}</p>
            <p className="text-xs text-slate-500 truncate">{node.description}</p>
          </div>
        </div>
        {hasChildren && isExpanded && (
          <div className="mt-1 space-y-1">
            {node.children!.map((child) => renderFeatureNode(child, depth + 1, nodeId))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to={`/runs/${runId}`} className="flex items-center gap-2 text-slate-600 hover:text-slate-900 group transition-all hover-lift">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回分析详情</span>
              </Link>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900">竞品知识 Schema</h1>
                <p className="text-xs text-slate-500 font-mono">{runId}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading || reportQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-64 w-full rounded-xl" />
          </div>
        ) : (
          <>
            {/* Tab Navigation */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-6">
              <div className="flex gap-2">
                <Button
                  variant={activeTab === "features" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveTab("features")}
                  className={cn(
                    "gap-2 transition-all hover-lift",
                    activeTab === "features" ? "bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-500/25" : "border-slate-300",
                  )}
                >
                  <Layers className="h-4 w-4" />
                  功能树
                </Button>
                <Button
                  variant={activeTab === "pricing" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveTab("pricing")}
                  className={cn(
                    "gap-2 transition-all hover-lift",
                    activeTab === "pricing" ? "bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-500/25" : "border-slate-300",
                  )}
                >
                  <DollarSign className="h-4 w-4" />
                  定价模型
                </Button>
                <Button
                  variant={activeTab === "users" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveTab("users")}
                  className={cn(
                    "gap-2 transition-all hover-lift",
                    activeTab === "users" ? "bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-500/25" : "border-slate-300",
                  )}
                >
                  <Users className="h-4 w-4" />
                  用户画像
                </Button>
              </div>
            </div>

            {/* Features Tab */}
            {activeTab === "features" && (
              <Card className="border-0 shadow-md overflow-hidden">
                <CardHeader className="pb-3 bg-gradient-to-r from-blue-50 to-purple-50/30 -mx-4 -mt-4 px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                        <Layers className="h-5 w-5" />
                        功能树结构
                      </CardTitle>
                      <p className="text-sm text-slate-500">展示竞品功能模块的层级结构和可用性</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-4 text-xs">
                        <span className="flex items-center gap-1">
                          <span className="w-3 h-3 rounded-full bg-green-500" />
                          <span className="text-slate-600">可用: {featureStats.available}</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="w-3 h-3 rounded-full bg-red-400" />
                          <span className="text-slate-600">缺失: {featureStats.unavailable}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4 pt-4">
                  {/* Search and Actions */}
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="relative flex-1 min-w-[200px] max-w-md">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <input
                        type="text"
                        placeholder="搜索功能..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 rounded-xl border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" onClick={expandAllFeatures} className="gap-2 border-slate-300">
                        <Expand className="h-4 w-4" />
                        展开全部
                      </Button>
                      <Button variant="outline" size="sm" onClick={collapseAllFeatures} className="gap-2 border-slate-300">
                        <ChevronDown className="h-4 w-4" />
                        收起全部
                      </Button>
                    </div>
                  </div>
                  {/* Feature Tree */}
                  <div className="bg-slate-50/50 rounded-xl p-2">
                    {renderFeatureNode(mockFeatureTree)}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Pricing Tab */}
            {activeTab === "pricing" && (
              <div className="grid gap-4 md:grid-cols-3">
                {mockPricingTiers.map((tier, index) => (
                  <Card
                    key={tier.name}
                    className={cn(
                      "border-0 shadow-md transition-all hover:shadow-xl hover:-translate-y-1 duration-300",
                      tier.popular && "border-2 border-blue-500 bg-gradient-to-br from-blue-50 to-white",
                    )}
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <CardHeader className="text-center pb-3">
                      {tier.popular && (
                        <span className="inline-block px-3 py-1 text-xs font-medium bg-blue-600 text-white rounded-full mb-2 animate-pulse">
                          推荐
                        </span>
                      )}
                      <CardTitle className="text-lg font-semibold text-slate-900">{tier.name}</CardTitle>
                      <div className="flex items-baseline justify-center gap-1 mt-2">
                        <DollarSign className="h-5 w-5 text-slate-600" />
                        <span className="text-3xl font-bold text-slate-900">{tier.price}</span>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <ul className="space-y-2">
                        {tier.features.map((feature, idx) => (
                          <li key={feature} className="flex items-center gap-2 text-sm text-slate-700 animate-in fade-in slide-in-from-left-2" style={{ animationDelay: `${idx * 50}ms` }}>
                            <Check className="h-4 w-4 text-green-600 flex-shrink-0" />
                            {feature}
                          </li>
                        ))}
                      </ul>
                      <Button className="w-full mt-4 transition-all hover-lift" variant={tier.popular ? "default" : "outline"}>
                        {tier.popular ? "立即开始" : "了解详情"}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {/* Users Tab */}
            {activeTab === "users" && (
              <div className="space-y-4">
                {mockUserProfiles.map((profile, index) => (
                  <Card 
                    key={profile.segment} 
                    className="border-0 shadow-md transition-all hover:shadow-lg hover:-translate-y-1 duration-300"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                            <Users className="h-5 w-5" />
                            {profile.segment}
                          </CardTitle>
                          <p className="text-sm text-slate-500">{profile.description}</p>
                        </div>
                        <span className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded-full">
                          用户群体
                        </span>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="animate-in fade-in slide-in-from-left-2">
                        <h4 className="text-sm font-medium text-slate-700 mb-2">核心需求</h4>
                        <div className="flex flex-wrap gap-2">
                          {profile.needs.map((need) => (
                            <span
                              key={need}
                              className="px-3 py-1 text-xs bg-gradient-to-r from-blue-100 to-purple-100 text-blue-700 rounded-full transition-all hover:scale-105 hover:shadow-md"
                            >
                              {need}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="animate-in fade-in slide-in-from-left-2" style={{ animationDelay: "100ms" }}>
                        <h4 className="text-sm font-medium text-slate-700 mb-2">使用模式</h4>
                        <ul className="space-y-2">
                          {profile.usage_patterns.map((pattern) => (
                            <li key={pattern} className="flex items-center gap-2 text-sm text-slate-600">
                              <div className="w-2 h-2 rounded-full bg-gradient-to-br from-blue-500 to-purple-600" />
                              {pattern}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}

        {/* Error State */}
        {detailQuery.isError || reportQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">数据读取失败</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {detailQuery.error?.message ?? reportQuery.error?.message ?? "unknown error"}
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