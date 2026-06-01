import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { 
  Activity, 
  Cpu, 
  Clock, 
  TrendingUp, 
  CheckCircle2,
  Sparkles,
  Zap,
  Server,
  Database,
  BarChart3,
  Eye,
  ArrowRight,
  Settings,
  RefreshCw
} from "lucide-react";

import { useDashboard, useRunsList } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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
    const initialParticles: Particle[] = Array.from({ length: 25 }, (_, i) => ({
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
          className="absolute rounded-full bg-gradient-to-br from-blue-500/40 to-cyan-500/40 animate-breathe"
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

const AGENT_COLORS: Record<string, string> = {
  supervisor: "from-purple-500 to-violet-600",
  researcher: "from-blue-500 to-cyan-600",
  analyst: "from-green-500 to-emerald-600",
  writer: "from-orange-500 to-amber-600",
  qa: "from-red-500 to-rose-600",
  skill_curator: "from-indigo-500 to-purple-600",
};

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const [isVisible, setIsVisible] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");

  const dashboardQuery = useDashboard();
  const runsQuery = useRunsList({ limit: 5 });

  useEffect(() => {
    setIsVisible(true);
  }, []);

  const dashboardData = dashboardQuery.data;
  const recentRuns = runsQuery.data?.items.slice(0, 5) || [];

  const formatTokenCount = (tokens: number): string => {
    if (tokens >= 1000000) {
      return `${(tokens / 1000000).toFixed(1)}M`;
    } else if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(1)}K`;
    }
    return tokens.toString();
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return "-";
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 relative">
      <ParticleBackground />
      
      {/* Grid Pattern */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.08),transparent_70%)]" />

      {/* Header */}
      <header className={`sticky top-0 z-50 bg-slate-900/80 backdrop-blur-lg border-b border-slate-700/50 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"}`}>
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Left: Logo */}
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 group-hover:rotate-12">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg blur-md opacity-50 group-hover:opacity-75" />
              </div>
              <span className="font-semibold text-white">RivalLens</span>
            </Link>
            
            {/* Center: Navigation */}
            <nav className="flex items-center gap-1">
              <Link
                to="/"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                首页
              </Link>
              <Link
                to="/features"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                功能介绍
              </Link>
              <Link
                to="/runs"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                任务列表
              </Link>
              <Link
                to="/dashboard"
                className="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-blue-400 relative"
              >
                监控仪表盘
                <span className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-cyan-500/30 rounded-lg animate-pulse-glow" />
              </Link>
              <Link
                to="/feedback"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                反馈闭环
              </Link>
              <Link
                to="/skills/staging"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                Skill 审核台
              </Link>
            </nav>
            
            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              <Button 
                size="sm" 
                variant="outline"
                className="border-slate-600 text-slate-300 hover:bg-slate-800 hover:border-slate-500"
              >
                <Settings className="h-4 w-4 mr-2" />
                设置
              </Button>
              <Button 
                size="sm" 
                onClick={() => navigate("/runs/new")}
                className="group relative overflow-hidden bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 text-white"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-4 w-4 mr-1" />
                  开始分析
                </span>
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Page Header */}
        <div className={`mb-8 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white mb-2">Agent 监控仪表盘</h1>
              <p className="text-slate-400">实时监控多 Agent 协作系统的运行状态和性能指标</p>
            </div>
            <Button 
              variant="outline"
              className="border-slate-600 text-slate-300 hover:bg-slate-800"
              onClick={() => dashboardQuery.refetch()}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${dashboardQuery.isFetching ? "animate-spin" : ""}`} />
              刷新数据
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className={`flex gap-2 mb-8 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "50ms" }}>
          {["overview", "agents", "metrics", "logs"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                activeTab === tab
                  ? "bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-blue-400 border border-blue-500/30"
                  : "text-slate-400 hover:bg-slate-800"
              )}
            >
              {tab === "overview" && "概览"}
              {tab === "agents" && "Agent 状态"}
              {tab === "metrics" && "性能指标"}
              {tab === "logs" && "运行日志"}
            </button>
          ))}
        </div>

        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className={`grid grid-cols-2 md:grid-cols-4 gap-4 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "100ms" }}>
              {dashboardQuery.isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i} className="bg-slate-800/50 border-slate-700/50">
                    <CardContent className="p-5">
                      <Skeleton className="h-10 w-10 rounded-xl mb-4" />
                      <Skeleton className="h-8 w-24 mb-1" />
                      <Skeleton className="h-4 w-32" />
                    </CardContent>
                  </Card>
                ))
              ) : (
                [
                  { 
                    label: "总任务数", 
                    value: dashboardData?.metrics.total_runs ?? 0, 
                    change: "+12%", 
                    color: "from-blue-500 to-blue-600", 
                    icon: Activity 
                  },
                  { 
                    label: "Token消耗", 
                    value: formatTokenCount(dashboardData?.metrics.total_tokens ?? 0), 
                    change: "+8%", 
                    color: "from-purple-500 to-violet-600", 
                    icon: Zap 
                  },
                  { 
                    label: "平均耗时", 
                    value: formatDuration(dashboardData?.metrics.avg_run_duration_seconds ?? null), 
                    change: "-5%", 
                    color: "from-green-500 to-emerald-600", 
                    icon: Clock 
                  },
                  { 
                    label: "成功率", 
                    value: `${dashboardData?.metrics.overall_success_rate ?? 0}%`, 
                    change: "+0.5%", 
                    color: "from-cyan-500 to-teal-600", 
                    icon: CheckCircle2 
                  },
                ].map((metric, index) => (
                  <Card 
                    key={metric.label}
                    className="bg-slate-800/50 border-slate-700/50 backdrop-blur-sm hover-lift"
                    style={{ transitionDelay: `${150 + index * 50}ms` }}
                  >
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between">
                        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${metric.color} flex items-center justify-center`}>
                          <metric.icon className="h-5 w-5 text-white" />
                        </div>
                        <span className="text-xs text-green-400 font-medium">{metric.change}</span>
                      </div>
                      <div className="mt-4">
                        <p className="text-2xl font-bold text-white">{metric.value}</p>
                        <p className="text-sm text-slate-400 mt-1">{metric.label}</p>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Agent Status */}
              <Card className={`bg-slate-800/50 border-slate-700/50 backdrop-blur-sm transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "200ms" }}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <Server className="h-5 w-5 text-blue-400" />
                    Agent 运行状态
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {dashboardQuery.isLoading ? (
                    <div className="space-y-3">
                      {Array.from({ length: 6 }).map((_, i) => (
                        <Skeleton key={i} className="h-14 w-full rounded-xl" />
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {dashboardData?.agent_status.map((agent) => (
                        <div 
                          key={agent.agent_name}
                          className="flex items-center justify-between p-3 rounded-xl bg-slate-700/30 hover:bg-slate-700/50 transition-all cursor-pointer group"
                          onClick={() => setSelectedAgent(agent.agent_name)}
                        >
                          <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${AGENT_COLORS[agent.agent_name] || "from-slate-500 to-slate-600"} flex items-center justify-center`}>
                              <Cpu className="h-5 w-5 text-white" />
                            </div>
                            <div>
                              <p className="font-medium text-white group-hover:text-blue-400 transition-colors">{agent.agent_name}</p>
                              <p className="text-xs text-slate-400">{agent.role}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-slate-400">{agent.task_count} 任务</span>
                            <span className={cn(
                              "w-2 h-2 rounded-full",
                              agent.status === "active" ? "bg-green-400 animate-pulse" : "bg-slate-500"
                            )} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Recent Runs */}
              <Card className={`bg-slate-800/50 border-slate-700/50 backdrop-blur-sm transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "250ms" }}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <Activity className="h-5 w-5 text-cyan-400" />
                    最近任务
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {runsQuery.isLoading ? (
                    <div className="space-y-3">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Skeleton key={i} className="h-10 w-full rounded-lg" />
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {recentRuns.map((run) => (
                        <div 
                          key={run.run_id}
                          className="p-3 rounded-xl bg-slate-700/30 hover:bg-slate-700/50 transition-all cursor-pointer group"
                        >
                          <div className="flex items-center justify-between">
                            <p className="text-sm text-white line-clamp-1 group-hover:text-blue-400 transition-colors">
                              {run.user_query}
                            </p>
                            <span className={cn(
                              "px-2 py-1 rounded-full text-xs font-medium",
                              run.status === "running" && "bg-amber-500/20 text-amber-400",
                              run.status === "completed" && "bg-green-500/20 text-green-400",
                              run.status === "failed" && "bg-red-500/20 text-red-400",
                            )}>
                              {run.status === "running" ? "运行中" : run.status === "completed" ? "已完成" : "失败"}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                            <span>{run.evidence_count} 证据</span>
                            <span>{run.step_count} 步骤</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <Button 
                    variant="ghost" 
                    className="w-full mt-4 text-slate-400 hover:text-white hover:bg-slate-700/50"
                    onClick={() => navigate("/runs")}
                  >
                    查看全部任务
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Button>
                </CardContent>
              </Card>

              {/* DAG Flow */}
              <Card className={`bg-slate-800/50 border-slate-700/50 backdrop-blur-sm transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`} style={{ transitionDelay: "300ms" }}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-purple-400" />
                    任务流转 DAG
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="relative">
                    {/* Flow Diagram */}
                    <div className="flex flex-col gap-4">
                      {["Supervisor", "Researcher", "Analyst", "Writer", "QA", "Curator"].map((step, index) => (
                        <div key={step} className="relative">
                          <div className={cn(
                            "flex items-center gap-3 p-3 rounded-xl",
                            index % 2 === 0 ? "bg-gradient-to-r from-blue-500/10 to-purple-500/10" : "bg-gradient-to-r from-cyan-500/10 to-blue-500/10"
                          )}>
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
                              {step.charAt(0)}
                            </div>
                            <span className="text-white text-sm font-medium">{step}</span>
                            <CheckCircle2 className="h-4 w-4 text-green-400 ml-auto" />
                          </div>
                          {index < 5 && (
                            <div className="absolute left-[18px] top-full w-0.5 h-4 bg-gradient-to-b from-blue-500/50 to-purple-500/50" />
                          )}
                        </div>
                      ))}
                    </div>
                    
                    {/* Legend */}
                    <div className="mt-6 pt-4 border-t border-slate-700">
                      <p className="text-xs text-slate-400 mb-2">图例</p>
                      <div className="flex flex-wrap gap-3">
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full bg-green-400" />
                          <span className="text-xs text-slate-400">已完成</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full bg-blue-400" />
                          <span className="text-xs text-slate-400">执行中</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="w-3 h-3 rounded-full bg-slate-500" />
                          <span className="text-xs text-slate-400">待执行</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === "agents" && (
          <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
            {dashboardQuery.isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <Card key={i} className="bg-slate-800/50 border-slate-700/50">
                  <CardContent className="p-6">
                    <Skeleton className="h-12 w-12 rounded-xl mb-4" />
                    <Skeleton className="h-6 w-32 mb-2" />
                    <Skeleton className="h-4 w-48 mb-4" />
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <Skeleton className="h-8 w-12 mx-auto" />
                        <Skeleton className="h-4 w-16 mx-auto mt-1" />
                      </div>
                      <div>
                        <Skeleton className="h-8 w-12 mx-auto" />
                        <Skeleton className="h-4 w-16 mx-auto mt-1" />
                      </div>
                      <div>
                        <Skeleton className="h-8 w-12 mx-auto" />
                        <Skeleton className="h-4 w-16 mx-auto mt-1" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              dashboardData?.agent_status.map((agent, index) => (
                <Card 
                  key={agent.agent_name}
                  className={`bg-slate-800/50 border-slate-700/50 backdrop-blur-sm hover-lift cursor-pointer transition-all duration-500 ${selectedAgent === agent.agent_name ? "ring-2 ring-blue-500/50" : ""}`}
                  onClick={() => setSelectedAgent(selectedAgent === agent.agent_name ? null : agent.agent_name)}
                  style={{ transitionDelay: `${100 + index * 50}ms` }}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${AGENT_COLORS[agent.agent_name] || "from-slate-500 to-slate-600"} flex items-center justify-center`}>
                          <Cpu className="h-6 w-6 text-white" />
                        </div>
                        <div>
                          <CardTitle className="text-base font-semibold text-white">{agent.agent_name}</CardTitle>
                          <p className="text-xs text-slate-400">{agent.role}</p>
                        </div>
                      </div>
                      <span className={cn(
                        "px-3 py-1 rounded-full text-xs font-medium",
                        agent.status === "active" ? "bg-green-500/20 text-green-400" : "bg-slate-600/50 text-slate-400"
                      )}>
                        {agent.status === "active" ? "活跃" : "空闲"}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4 mb-4">
                      <div className="text-center">
                        <p className="text-xl font-bold text-white">{agent.task_count}</p>
                        <p className="text-xs text-slate-400">任务数</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xl font-bold text-white">{agent.success_rate}%</p>
                        <p className="text-xs text-slate-400">成功率</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xl font-bold text-white">{agent.avg_latency_ms}ms</p>
                        <p className="text-xs text-slate-400">平均耗时</p>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-400">CPU 使用率</span>
                          <span className="text-green-400">45%</span>
                        </div>
                        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div className="h-full w-[45%] bg-gradient-to-r from-green-500 to-emerald-500 rounded-full" />
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-400">内存使用</span>
                          <span className="text-blue-400">62%</span>
                        </div>
                        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div className="h-full w-[62%] bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full" />
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}

        {activeTab === "metrics" && (
          <div className={`space-y-6 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {dashboardQuery.isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i} className="bg-slate-800/50 border-slate-700/50">
                    <CardContent className="p-5">
                      <Skeleton className="h-4 w-32 mb-2" />
                      <Skeleton className="h-8 w-24" />
                    </CardContent>
                  </Card>
                ))
              ) : (
                [
                  { label: "LLM 调用次数", value: dashboardData?.metrics.total_llm_calls ?? 0, change: "+15%", color: "from-purple-500 to-violet-600" },
                  { label: "Token 消耗", value: formatTokenCount(dashboardData?.metrics.total_tokens ?? 0), change: "+8%", color: "from-blue-500 to-cyan-600" },
                  { label: "平均延迟", value: formatDuration(dashboardData?.metrics.avg_run_duration_seconds ?? null), change: "-12%", color: "from-green-500 to-emerald-600" },
                  { label: "运行中任务", value: `${dashboardData?.metrics.running_runs ?? 0}`, change: "+3", color: "from-cyan-500 to-teal-600" },
                ].map((metric) => (
                  <Card key={metric.label} className="bg-slate-800/50 border-slate-700/50 backdrop-blur-sm">
                    <CardContent className="p-5">
                      <p className="text-sm text-slate-400 mb-1">{metric.label}</p>
                      <div className="flex items-end justify-between">
                        <p className={`text-3xl font-bold bg-gradient-to-r ${metric.color} bg-clip-text text-transparent`}>
                          {metric.value}
                        </p>
                        <span className="text-xs text-green-400 mb-1">{metric.change}</span>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <Database className="h-5 w-5 text-blue-400" />
                    数据源分布
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {dashboardQuery.isLoading ? (
                    <div className="space-y-4">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <div key={i}>
                          <Skeleton className="h-4 w-full mb-2" />
                          <Skeleton className="h-3 w-full" />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {dashboardData?.source_distribution.map((item) => (
                        <div key={item.source_type}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-white">{item.source_type}</span>
                            <span className="text-slate-400">{item.percentage}%</span>
                          </div>
                          <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full transition-all duration-1000"
                              style={{ width: `${item.percentage}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-green-400" />
                    每日任务趋势
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {dashboardQuery.isLoading ? (
                    <div className="flex items-end justify-between h-40 gap-2">
                      {Array.from({ length: 7 }).map((_, i) => (
                        <Skeleton key={i} className="flex-1 rounded-t-lg" style={{ height: `${Math.random() * 100}%` }} />
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-end justify-between h-40 gap-2">
                      {dashboardData?.daily_stats.map((item) => (
                        <div key={item.date} className="flex-1 flex flex-col items-center gap-2">
                          <div 
                            className="w-full bg-gradient-to-t from-blue-500/50 to-cyan-500/50 rounded-t-lg transition-all duration-700 hover:from-blue-500 hover:to-cyan-500"
                            style={{ height: `${((item.count || 0) / 30) * 100}%` }}
                          />
                          <span className="text-xs text-slate-400">{formatDate(item.date)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === "logs" && (
          <div className={`transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
            <Card className="bg-slate-800/50 border-slate-700/50 backdrop-blur-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
                    <Activity className="h-5 w-5 text-orange-400" />
                    运行日志
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" className="border-slate-600 text-slate-400">
                      <Eye className="h-4 w-4 mr-2" />
                      查看详情
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 font-mono text-sm">
                  {[
                    { time: "14:32:15", level: "INFO", agent: "Supervisor", message: "任务调度开始，分配 researcher 执行调研任务" },
                    { time: "14:32:18", level: "DEBUG", agent: "Researcher", message: "开始采集竞品信息: Cursor" },
                    { time: "14:32:45", level: "INFO", agent: "Researcher", message: "完成 Cursor 信息采集，获取 12 条证据" },
                    { time: "14:32:46", level: "DEBUG", agent: "Researcher", message: "开始采集竞品信息: GitHub Copilot" },
                    { time: "14:33:12", level: "INFO", agent: "Researcher", message: "完成 GitHub Copilot 信息采集，获取 15 条证据" },
                    { time: "14:33:15", level: "INFO", agent: "Supervisor", message: "调研阶段完成，分配 analyst 执行分析任务" },
                    { time: "14:33:20", level: "DEBUG", agent: "Analyst", message: "开始跨竞品对比分析" },
                    { time: "14:34:15", level: "INFO", agent: "Analyst", message: "分析完成，生成 SWOT 矩阵" },
                    { time: "14:34:18", level: "INFO", agent: "Supervisor", message: "分析阶段完成，分配 writer 生成报告" },
                    { time: "14:34:25", level: "DEBUG", agent: "Writer", message: "开始生成 Battlecard 报告" },
                    { time: "14:35:00", level: "INFO", agent: "Writer", message: "报告生成完成" },
                    { time: "14:35:05", level: "DEBUG", agent: "QA", message: "开始质量校验" },
                    { time: "14:35:18", level: "INFO", agent: "QA", message: "校验通过，报告质量优秀" },
                  ].map((log, index) => (
                    <div 
                      key={index}
                      className="flex items-start gap-4 p-3 rounded-lg bg-slate-700/30 hover:bg-slate-700/50 transition-colors"
                    >
                      <span className="text-slate-500 text-xs w-16 flex-shrink-0">{log.time}</span>
                      <span className={cn(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        log.level === "INFO" && "bg-blue-500/20 text-blue-400",
                        log.level === "DEBUG" && "bg-purple-500/20 text-purple-400",
                        log.level === "ERROR" && "bg-red-500/20 text-red-400",
                      )}>
                        {log.level}
                      </span>
                      <span className="text-green-400 text-xs font-medium w-24 flex-shrink-0">{log.agent}</span>
                      <span className="text-slate-300">{log.message}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-slate-900/80 backdrop-blur-sm border-t border-slate-800 mt-auto relative z-10">
        <div className="max-w-7xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-3">
            <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg flex items-center justify-center">
              <Sparkles className="h-3 w-3 text-white" />
            </div>
            <span className="font-semibold text-white">RivalLens</span>
          </div>
          <p className="text-sm text-slate-500">
            AI 驱动的竞品分析平台 | Agent 监控仪表盘
          </p>
        </div>
      </footer>
    </div>
  );
}
