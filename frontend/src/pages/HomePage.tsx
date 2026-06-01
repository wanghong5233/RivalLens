import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Brain, Clock, CheckCircle2, AlertCircle, Loader2, Target, Sparkles, TrendingUp, Lightbulb, Zap, ChevronRight } from "lucide-react";

import { useResumeRun, useRunsList } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/format";

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
    const initialParticles: Particle[] = Array.from({ length: 30 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 3 + 1,
      speedX: (Math.random() - 0.5) * 0.5,
      speedY: (Math.random() - 0.5) * 0.5,
      opacity: Math.random() * 0.5 + 0.2,
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
    }, 50);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute rounded-full bg-gradient-to-br from-blue-500 to-purple-600 animate-breathe"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            opacity: particle.opacity,
            animationDelay: `${particle.id * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
}

function ScanLine(): JSX.Element {
  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
      <div
        className="absolute w-full h-[2px] bg-gradient-to-r from-transparent via-blue-500/20 to-transparent animate-scan-line"
      />
    </div>
  );
}

function FloatingIcons(): JSX.Element {
  const icons = [
    { icon: Brain, color: "from-blue-500/30 to-cyan-500/30", delay: "0s", size: 60 },
    { icon: Target, color: "from-purple-500/30 to-pink-500/30", delay: "2s", size: 45 },
    { icon: TrendingUp, color: "from-green-500/30 to-emerald-500/30", delay: "4s", size: 55 },
    { icon: Lightbulb, color: "from-orange-500/30 to-yellow-500/30", delay: "1s", size: 50 },
    { icon: Zap, color: "from-amber-500/30 to-yellow-500/30", delay: "3s", size: 40 },
  ];

  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
      {icons.map((item, index) => (
        <div
          key={index}
          className={`absolute animate-float`}
          style={{
            left: `${15 + index * 18}%`,
            top: `${20 + (index % 3) * 25}%`,
            animationDelay: item.delay,
          }}
        >
          <div className={`w-${item.size} h-${item.size} bg-gradient-to-br ${item.color} rounded-full flex items-center justify-center backdrop-blur-sm`}>
            <item.icon className="w-1/2 h-1/2 text-white/60" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function HomePage(): JSX.Element {
  const navigate = useNavigate();
  const runsQuery = useRunsList({ limit: 5, offset: 0 });
  const resumeMutation = useResumeRun();
  const [resumingRunId, setResumingRunId] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  async function handleResumeRun(runId: string): Promise<void> {
    setResumingRunId(runId);
    try {
      await resumeMutation.mutateAsync(runId);
      setResumeError(null);
      await runsQuery.refetch();
      navigate(`/runs/${runId}`);
    } catch (error) {
      if (error instanceof Error) {
        setResumeError(error.message);
      } else {
        setResumeError("恢复运行失败，请稍后重试。");
      }
    } finally {
      setResumingRunId(null);
    }
  }

  const location = useLocation();
  
  const navItems = [
    { path: "/", label: "首页" },
    { path: "/features", label: "功能介绍" },
    { path: "/runs", label: "任务列表" },
    { path: "/dashboard", label: "监控仪表盘" },
    { path: "/feedback", label: "反馈闭环" },
    { path: "/skills/staging", label: "Skill 审核台" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 grid-bg">
      <ParticleBackground />
      <ScanLine />
      <FloatingIcons />

      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-slate-100/50 shadow-sm">
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
              {navItems.map((item, index) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 relative group ${
                    location.pathname === item.path
                      ? "bg-blue-50 text-blue-600"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  {item.label}
                  {location.pathname === item.path && (
                    <span className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-lg animate-pulse-glow" />
                  )}
                </Link>
              ))}
            </nav>
            
            {/* Right: Actions */}
            <div className="flex items-center gap-2">
              <Button 
                size="sm" 
                onClick={() => navigate("/runs/new")}
                className="relative overflow-hidden bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white group"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-4 w-4 mr-1" />
                  开始分析
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-purple-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-16 px-4">
        <div className="absolute top-20 right-10 w-96 h-96 bg-gradient-to-br from-blue-400/20 to-purple-400/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 left-10 w-80 h-80 bg-gradient-to-br from-cyan-400/20 to-blue-400/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />
        
        <div className="relative max-w-4xl mx-auto">
          <div className="text-center">
            <div className={`inline-flex items-center gap-2 px-4 py-2 mb-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-full text-white text-sm font-medium shadow-lg shadow-blue-500/25 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}>
              <Sparkles className="h-4 w-4 animate-spin-slow" />
              AI 驱动的智能竞品分析
            </div>
            
            <h1 className={`text-4xl md:text-5xl lg:text-6xl font-bold text-slate-900 mb-6 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "100ms" }}>
              <span className="gradient-text glow-text">RivalLens</span>
              <span className="block text-xl md:text-2xl lg:text-3xl font-light text-slate-600 mt-2">
                让竞品分析更智能、更高效
              </span>
            </h1>
            
            <p className={`text-lg md:text-xl text-slate-600 mb-12 max-w-4xl mx-auto transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "200ms" }}>
              多 Agent 协作系统，模拟专业调研团队，自动完成信息采集、分析对比到报告生成的全流程
            </p>
            
            <div className={`flex flex-col sm:flex-row gap-4 justify-center mb-16 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "300ms" }}>
              <Button 
                size="lg" 
                onClick={() => navigate("/runs/new")}
                className="group relative overflow-hidden bg-gradient-to-r from-blue-600 via-purple-600 to-blue-700 hover:from-blue-700 hover:via-purple-700 hover:to-blue-800 text-white px-10 py-7 text-lg font-semibold shadow-xl shadow-blue-600/30"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-5 w-5 mr-2" />
                  开始新分析
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
              </Button>
              <Button 
                size="lg" 
                onClick={() => navigate("/features")}
                className="group relative overflow-hidden bg-white text-blue-600 border-2 border-blue-200 hover:border-blue-400 hover:bg-blue-50 px-10 py-7 text-lg font-semibold shadow-lg"
              >
                <span className="relative z-10 flex items-center">
                  了解更多
                  <ChevronRight className="h-5 w-5 ml-2 group-hover:translate-x-1 transition-transform" />
                </span>
              </Button>
            </div>

            {/* Agent Workflow */}
            <div className={`bg-white rounded-3xl p-8 border border-slate-100 shadow-xl transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "400ms" }}>
              <h3 className="text-lg font-semibold text-slate-900 mb-8 text-center">工作流程</h3>
              <div className="flex flex-wrap justify-center items-center gap-2">
                {[
                  { name: "调度", icon: <Brain className="h-6 w-6" />, color: "from-blue-500 to-blue-600", delay: "0ms" },
                  { name: "调研", icon: <Target className="h-6 w-6" />, color: "from-green-500 to-green-600", delay: "100ms" },
                  { name: "分析", icon: <TrendingUp className="h-6 w-6" />, color: "from-purple-500 to-purple-600", delay: "200ms" },
                  { name: "撰写", icon: <Lightbulb className="h-6 w-6" />, color: "from-orange-500 to-orange-600", delay: "300ms" },
                  { name: "质检", icon: <CheckCircle2 className="h-6 w-6" />, color: "from-cyan-500 to-cyan-600", delay: "400ms" },
                ].map((agent, index) => (
                  <div key={agent.name} className="flex items-center">
                    <div 
                      className="flex flex-col items-center group"
                      style={{ transitionDelay: agent.delay }}
                    >
                      <div className={`relative group-hover:scale-110 transition-transform duration-300`}>
                        <div className={`w-16 h-16 bg-gradient-to-br ${agent.color} rounded-2xl flex items-center justify-center text-white shadow-lg`}>
                          {agent.icon}
                        </div>
                        <div className={`absolute inset-0 bg-gradient-to-br ${agent.color} rounded-2xl blur-md opacity-0 group-hover:opacity-50 transition-opacity`} />
                      </div>
                      <span className="mt-3 text-sm font-medium text-slate-700 group-hover:text-slate-900 transition-colors">{agent.name}</span>
                    </div>
                    {index < 4 && (
                      <div className="relative mx-3">
                        <ArrowRight className="h-5 w-5 text-slate-300" />
                        <div className="absolute inset-0 bg-blue-500/20 blur-md" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-16 px-4 bg-white relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-blue-50/50 to-transparent" />
        <div className="max-w-5xl mx-auto relative">
          <div className="text-center mb-12">
            <h2 className="text-2xl md:text-3xl font-bold text-slate-900 mb-4 gradient-text">为什么选择 RivalLens</h2>
            <p className="text-slate-600">AI 驱动，让竞品分析更智能</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { icon: Brain, title: "智能分析", desc: "多 Agent 协作，自动完成从信息采集到报告生成的全流程", color: "from-blue-500 to-blue-600", delay: "0ms" },
              { icon: TrendingUp, title: "数据驱动", desc: "基于真实数据进行分析，结论可溯源，证据可验证", color: "from-green-500 to-green-600", delay: "100ms" },
              { icon: Zap, title: "高效协作", desc: "模拟专业调研团队，分工明确，高效完成分析任务", color: "from-purple-500 to-purple-600", delay: "200ms" },
            ].map((feature) => (
              <Card 
                key={feature.title}
                className="border-0 shadow-lg shadow-slate-100/50 hover-lift tech-border overflow-hidden"
                style={{ transitionDelay: feature.delay }}
              >
                <CardContent className="p-6">
                  <div className={`relative w-14 h-14 bg-gradient-to-br ${feature.color} rounded-2xl flex items-center justify-center text-white mb-4 group-hover:scale-110 transition-transform duration-300`}>
                    <feature.icon className="h-7 w-7" />
                    <div className={`absolute inset-0 bg-gradient-to-br ${feature.color} rounded-2xl blur-md opacity-0 group-hover:opacity-50 transition-opacity`} />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2 group-hover:text-blue-600 transition-colors">{feature.title}</h3>
                  <p className="text-slate-600 text-sm">{feature.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Recent Runs Section */}
      <section className="py-16 px-4 bg-slate-50">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-2xl font-bold text-slate-900 gradient-text">最近分析任务</h2>
              <p className="text-slate-500 mt-1">查看最近的分析记录</p>
            </div>
            <Button onClick={() => navigate("/runs/new")} size="sm" className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white group">
              <ArrowRight className="h-4 w-4 mr-2 group-hover:translate-x-1 transition-transform" />
              新建分析
            </Button>
          </div>

          {/* Loading State */}
          {runsQuery.isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Card key={i} className="border-0 shadow-md animate-pulse">
                  <CardContent className="p-6">
                    <div className="space-y-3">
                      <Skeleton className="h-5 w-64" />
                      <Skeleton className="h-4 w-96" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : null}

          {/* Error State */}
          {runsQuery.isError ? (
            <Card className="border-0 shadow-md bg-amber-50 animate-scale-in">
              <CardContent className="p-6">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                    <AlertCircle className="h-5 w-5 text-amber-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-amber-800">无法获取分析任务列表</p>
                    <p className="text-xs text-amber-600 mt-1">
                      {runsQuery.error.message}
                    </p>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="mt-3 border-amber-300 text-amber-700 hover:bg-amber-100"
                      onClick={() => runsQuery.refetch()}
                    >
                      重新加载
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {/* Resume Error */}
          {resumeError ? (
            <Card className="border-0 shadow-md bg-amber-50 mb-4 animate-scale-in">
              <CardContent className="p-6">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                    <AlertCircle className="h-5 w-5 text-amber-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-amber-800">恢复运行失败</p>
                    <p className="text-xs text-amber-600 mt-1">
                      {resumeError}
                    </p>
                    <p className="text-xs text-amber-600 mt-1">
                      分析任务可能仍在后台运行，您可以点击"查看详情"查看任务状态。
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {/* Empty State */}
          {!runsQuery.isLoading && !runsQuery.isError && runsQuery.data?.items.length === 0 ? (
            <Card className="border-0 shadow-md animate-slide-up">
              <CardContent className="pt-16 pb-16 text-center">
                <div className="relative w-20 h-20 mx-auto mb-6">
                  <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center shadow-lg animate-pulse-glow">
                    <Target className="h-10 w-10 text-white" />
                  </div>
                </div>
                <h3 className="text-xl font-semibold text-slate-900 mb-3">开始您的第一次分析</h3>
                <p className="text-slate-500 mb-8 max-w-md mx-auto">
                  体验 AI 驱动的智能竞品分析能力
                </p>
                <Button size="lg" onClick={() => navigate("/runs/new")} className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white group">
                  <ArrowRight className="h-5 w-5 mr-2 group-hover:translate-x-1 transition-transform" />
                  开始新分析
                </Button>
              </CardContent>
            </Card>
          ) : null}

          {/* Runs List */}
          {!runsQuery.isLoading && !runsQuery.isError && runsQuery.data?.items && runsQuery.data.items.length > 0 ? (
            <div className="space-y-4">
              {runsQuery.data?.items.map((run, index) => (
                <Card 
                  key={run.run_id}
                  className="cursor-pointer border-0 shadow-md hover:shadow-xl transition-all duration-300 tech-border"
                  onClick={() => navigate(`/runs/${run.run_id}`)}
                  role="button"
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-base font-semibold text-slate-900 truncate group-hover:text-blue-600 transition-colors">
                            {run.user_query}
                          </h3>
                          <StatusBadge status={run.status} />
                        </div>
                        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-500">
                          <span className="flex items-center gap-1">
                            <Clock className="h-4 w-4" />
                            {formatRelativeTime(run.started_at)}
                          </span>
                          <span>领域: {run.domain_hint ?? "未指定"}</span>
                          <span>{run.evidence_count} 条证据</span>
                          {run.has_report && (
                            <span className="flex items-center gap-1 text-green-600">
                              <CheckCircle2 className="h-4 w-4" />
                              已生成报告
                            </span>
                          )}
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3 ml-4">
                        {run.status === "running" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={resumingRunId === run.run_id}
                            onClick={(event) => {
                              event.stopPropagation();
                              void handleResumeRun(run.run_id);
                            }}
                            className="group border-blue-200 text-blue-600 hover:bg-blue-50"
                          >
                            {resumingRunId === run.run_id ? (
                              <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                恢复中...
                              </>
                            ) : (
                              <>
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                                恢复运行
                              </>
                            )}
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate(`/runs/${run.run_id}`);
                          }}
                          className="group text-slate-600 hover:text-blue-600"
                        >
                          查看详情
                          <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : null}
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 px-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-purple-600 to-blue-700 animate-gradient-shift" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.1),transparent_70%)]" />
        
        <div className="max-w-3xl mx-auto text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-4 py-2 mb-6 bg-white/10 rounded-full text-white text-sm font-medium backdrop-blur-sm">
            <Zap className="h-4 w-4" />
            立即体验
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4 glow-text">准备好开始竞品分析了吗？</h2>
          <p className="text-blue-100 mb-8 text-lg">
            创建您的第一个分析任务，体验 AI 驱动的智能分析能力
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button 
              size="lg"
              className="group relative overflow-hidden bg-white text-blue-600 hover:bg-blue-50 px-10 py-6 text-lg font-semibold shadow-xl"
              onClick={() => navigate("/runs/new")}
            >
              <span className="relative z-10 flex items-center">
                <ArrowRight className="h-5 w-5 mr-2" />
                开始新分析
              </span>
              <div className="absolute inset-0 bg-gradient-to-r from-blue-100 to-purple-100 opacity-0 group-hover:opacity-100 transition-opacity" />
            </Button>
            <Button 
              size="lg"
              className="group relative overflow-hidden bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white hover:bg-white/20 px-10 py-6 text-lg font-semibold"
              onClick={() => navigate("/features")}
            >
              <span className="relative z-10 flex items-center">
                了解更多
                <ChevronRight className="h-5 w-5 ml-2 group-hover:translate-x-1 transition-transform" />
              </span>
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100">
        <div className="max-w-3xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
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