import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { 
  ArrowRight, 
  Clock, 
  FileText, 
  Activity, 
  CheckCircle2, 
  AlertCircle, 
  Sparkles,
  Search,
  Filter,
  Zap,
  TrendingUp
} from "lucide-react";

import { useRunsList } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  speedX: number;
  speedY: number;
  opacity: number;
}

function ParticleBackground(): JSX.Element {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    const initialParticles: Particle[] = Array.from({ length: 20 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 2 + 1,
      speedX: (Math.random() - 0.5) * 0.2,
      speedY: (Math.random() - 0.5) * 0.2,
      opacity: Math.random() * 0.3 + 0.1,
    }));
    setParticles(initialParticles);

    const interval = setInterval(() => {
      setParticles((prev) =>
        prev.map((p) => ({
          ...p,
          x: (p.x + p.speedX + 100) % 100,
          y: (p.y + p.speedY + 100) % 100,
        }))
      );
    }, 80);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute rounded-full bg-gradient-to-br from-blue-500/40 to-purple-600/40 animate-breathe"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            opacity: particle.opacity,
            animationDelay: `${particle.id * 0.15}s`,
          }}
        />
      ))}
    </div>
  );
}

const STATUS_FILTERS = [
  { value: "", label: "全部" },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "degraded", label: "部分完成" },
  { value: "failed", label: "失败" },
];

export function RunListPage(): JSX.Element {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isVisible, setIsVisible] = useState(false);
  const [animatedCards, setAnimatedCards] = useState<boolean[]>([]);

  const runsQuery = useRunsList({ status: statusFilter || undefined });

  useEffect(() => {
    setIsVisible(true);
  }, []);

  useEffect(() => {
    if (runsQuery.data?.items) {
      setAnimatedCards(new Array(runsQuery.data.items.length).fill(false));
      
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              const index = parseInt(entry.target.getAttribute("data-card-index") || "0");
              setAnimatedCards((prev) => {
                const newArr = [...prev];
                newArr[index] = true;
                return newArr;
              });
            }
          });
        },
        { threshold: 0.1 }
      );

      setTimeout(() => {
        document.querySelectorAll("[data-card-index]").forEach((el) => {
          observer.observe(el);
        });
      }, 200);

      return () => observer.disconnect();
    }
  }, [runsQuery.data]);

  const filteredRuns = runsQuery.data?.items.filter((run) =>
    run.user_query.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 relative">
      <ParticleBackground />

      {/* Header */}
      <header className={`sticky top-0 z-50 glass border-b border-slate-100/50 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"}`}>
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Left: Logo */}
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 group-hover:rotate-12">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg blur-md opacity-50 group-hover:opacity-75" />
              </div>
              <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
            </Link>
            
            {/* Center: Navigation */}
            <nav className="flex items-center gap-1">
              <Link
                to="/"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                首页
              </Link>
              <Link
                to="/features"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                功能介绍
              </Link>
              <Link
                to="/runs"
                className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-50 text-blue-600 relative"
              >
                任务列表
                <span className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-lg animate-pulse-glow" />
              </Link>
              <Link
                to="/dashboard"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                监控仪表盘
              </Link>
              <Link
                to="/feedback"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                反馈闭环
              </Link>
              <Link
                to="/skills/staging"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                Skill 审核台
              </Link>
            </nav>
            
            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              <Button 
                size="sm" 
                onClick={() => navigate("/runs/new")}
                className="group relative overflow-hidden bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-4 w-4 mr-1" />
                  开始分析
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-purple-500 opacity-0 group-hover:opacity-100 transition-opacity" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Page Header */}
        <div className={`mb-8 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
          <h1 className="text-3xl font-bold text-slate-900 mb-2 gradient-text">分析任务列表</h1>
          <p className="text-slate-600">管理和查看所有竞品分析任务</p>
        </div>

        {/* Filters */}
        <div className={`flex flex-col sm:flex-row gap-4 mb-6 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "100ms" }}>
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="搜索分析问题..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white/80 backdrop-blur-sm text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 transition-all"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400" />
            <div className="flex gap-1">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  onClick={() => setStatusFilter(filter.value)}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                    statusFilter === filter.value
                      ? "bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-md"
                      : "bg-white/80 backdrop-blur-sm text-slate-600 hover:bg-slate-100 border border-slate-200"
                  )}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className={`grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "150ms" }}>
          {[
            { label: "总任务", value: runsQuery.data?.total || 0, color: "from-blue-500 to-blue-600" },
            { label: "运行中", value: runsQuery.data?.items.filter(r => r.status === "running").length || 0, color: "from-amber-500 to-orange-600" },
            { label: "已完成", value: runsQuery.data?.items.filter(r => r.status === "completed").length || 0, color: "from-green-500 to-emerald-600" },
            { label: "报告数", value: runsQuery.data?.items.filter(r => r.has_report).length || 0, color: "from-purple-500 to-violet-600" },
          ].map((stat) => (
            <div key={stat.label} className="p-4 bg-white/60 backdrop-blur-sm rounded-xl border border-slate-100 hover-lift">
              <div className="text-xs text-slate-500 mb-1">{stat.label}</div>
              <div className={`text-2xl font-bold bg-gradient-to-r ${stat.color} bg-clip-text text-transparent`}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        {/* Loading State */}
        {runsQuery.isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i} className="border-0 shadow-md">
                <CardContent className="p-6">
                  <div className="space-y-3">
                    <Skeleton className="h-5 w-3/4 rounded" />
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <Skeleton className="h-4 w-20 rounded" />
                        <Skeleton className="h-4 w-24 rounded" />
                      </div>
                      <Skeleton className="h-8 w-24 rounded" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        {/* Error State */}
        {runsQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-8 text-center">
              <AlertCircle className="h-12 w-12 text-amber-500 mx-auto mb-4" />
              <p className="text-slate-700 font-medium mb-2">加载任务列表失败</p>
              <p className="text-sm text-slate-500 mb-4">{runsQuery.error.message}</p>
              <Button onClick={() => runsQuery.refetch()} className="bg-amber-500 hover:bg-amber-600 text-white">
                重新加载
              </Button>
            </CardContent>
          </Card>
        ) : null}

        {/* Run List */}
        {!runsQuery.isLoading && !runsQuery.isError && filteredRuns.length > 0 ? (
          <div className="space-y-4">
            {filteredRuns.map((run, index) => (
              <Card 
                key={run.run_id}
                data-card-index={index}
                className={`group border-0 shadow-lg shadow-slate-100/50 overflow-hidden transition-all duration-500 hover-lift ${animatedCards[index] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}
                style={{ transitionDelay: `${index * 80}ms` }}
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <div className={cn(
                          "w-10 h-10 rounded-xl flex items-center justify-center",
                          run.status === "running" && "bg-gradient-to-br from-amber-500 to-orange-600",
                          run.status === "completed" && "bg-gradient-to-br from-green-500 to-emerald-600",
                          run.status === "degraded" && "bg-gradient-to-br from-yellow-500 to-amber-600",
                          run.status === "failed" && "bg-gradient-to-br from-red-500 to-rose-600",
                        )}>
                          {run.status === "running" && <Activity className="h-5 w-5 text-white animate-pulse" />}
                          {run.status === "completed" && <CheckCircle2 className="h-5 w-5 text-white" />}
                          {run.status === "degraded" && <AlertCircle className="h-5 w-5 text-white" />}
                          {run.status === "failed" && <AlertCircle className="h-5 w-5 text-white" />}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors line-clamp-1">
                            {run.user_query}
                          </p>
                          <div className="flex items-center gap-4 text-xs text-slate-500 mt-1">
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatRelativeTime(run.started_at)}
                            </span>
                            {run.domain_hint && (
                              <span className="px-2 py-0.5 bg-slate-100 rounded-full">{run.domain_hint}</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Metrics */}
                      <div className="flex items-center gap-6 mt-4 pl-13">
                        <div className="flex items-center gap-1.5">
                          <FileText className="h-4 w-4 text-slate-400" />
                          <span className="text-sm text-slate-600">{run.evidence_count} 条证据</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <TrendingUp className="h-4 w-4 text-slate-400" />
                          <span className="text-sm text-slate-600">{run.step_count} 个步骤</span>
                        </div>
                        {run.has_report && (
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            已生成报告
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                      <StatusBadge status={run.status} />
                      <Link
                        to={`/runs/${run.run_id}`}
                        className="flex items-center gap-1 px-4 py-2 bg-gradient-to-r from-blue-500/10 to-purple-500/10 text-blue-600 rounded-lg text-sm font-medium hover:from-blue-500/20 hover:to-purple-500/20 transition-all group"
                      >
                        查看详情
                        <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                      </Link>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        {/* Empty State */}
        {!runsQuery.isLoading && !runsQuery.isError && filteredRuns.length === 0 ? (
          <Card className="border-0 shadow-md bg-gradient-to-br from-slate-50 to-white">
            <CardContent className="p-12 text-center">
              <div className="w-20 h-20 bg-gradient-to-br from-blue-100 to-purple-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <Sparkles className="h-10 w-10 text-blue-500" />
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">
                {searchQuery ? "未找到匹配的任务" : "还没有分析任务"}
              </h3>
              <p className="text-slate-600 mb-6">
                {searchQuery ? "尝试调整搜索关键词或筛选条件" : "开始您的第一个竞品分析任务"}
              </p>
              <Button 
                onClick={() => navigate("/runs/new")}
                className="group relative overflow-hidden bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white px-8"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-5 w-5 mr-2" />
                  创建第一个分析任务
                </span>
              </Button>
            </CardContent>
          </Card>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white/80 backdrop-blur-sm border-t border-slate-100/50 mt-auto relative z-10">
        <div className="max-w-5xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-3">
            <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <Sparkles className="h-3 w-3 text-white" />
            </div>
            <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
          </div>
          <p className="text-sm text-slate-500">
            AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}
