import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Sparkles, Zap, User, Users, Briefcase, Building, X, Check, AlertCircle, Loader2 } from "lucide-react";

import { useCompetitorSeeds, useCreateRun } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ROLE_OPTIONS: Array<{ id: string; label: string; icon: typeof User }> = [
  { id: "pm", label: "产品经理", icon: Briefcase },
  { id: "founder", label: "创业者", icon: Building },
  { id: "sales", label: "销售", icon: Users },
  { id: "investor", label: "投资人", icon: User },
];

const SUGGESTED_COMPETITORS = [
  "Cursor", "GitHub Copilot", "Notion", "Obsidian", 
  "Linear", "Jira", "ClickUp", "Asana"
];

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
      speedX: (Math.random() - 0.5) * 0.3,
      speedY: (Math.random() - 0.5) * 0.3,
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
          className="absolute rounded-full bg-gradient-to-br from-blue-500/60 to-purple-600/60 animate-breathe"
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

export function NewRunPage(): JSX.Element {
  const navigate = useNavigate();
  const competitorSeedsQuery = useCompetitorSeeds();
  const createRunMutation = useCreateRun();

  const [userQuery, setUserQuery] = useState("");
  const [domainHint, setDomainHint] = useState("");
  const [competitorInput, setCompetitorInput] = useState("");
  const [selectedCompetitors, setSelectedCompetitors] = useState<string[]>([]);
  const [referenceUrlInput, setReferenceUrlInput] = useState("");
  const [referenceUrls, setReferenceUrls] = useState<string[]>([]);
  const [targetRoles, setTargetRoles] = useState<string[]>(["pm", "founder"]);
  const [showCompetitorWarning, setShowCompetitorWarning] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [focusedField, setFocusedField] = useState<string | null>(null);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  const fallbackCompetitors = SUGGESTED_COMPETITORS.map((name) => ({
    id: name.toLowerCase().replace(/\s+/g, "_"),
    display_name: name,
    aliases: [],
    official_url: null,
    category: null,
  }));
  
  const hasValidSeeds = competitorSeedsQuery.data && competitorSeedsQuery.data.length > 0;
  const competitorSeeds = hasValidSeeds ? competitorSeedsQuery.data : fallbackCompetitors;
  
  const competitorSuggestions = useMemo(() => {
    const keyword = competitorInput.trim().toLowerCase();
    const matched = competitorSeeds.filter((item) => {
      if (!keyword) {
        return true;
      }
      if (item.display_name.toLowerCase().includes(keyword)) {
        return true;
      }
      if (item.id.toLowerCase().includes(keyword)) {
        return true;
      }
      return item.aliases.some((alias) => alias.toLowerCase().includes(keyword));
    });
    return matched.slice(0, 8);
  }, [competitorInput, competitorSeeds]);

  useEffect(() => {
    if (selectedCompetitors.length > 0) {
      return;
    }
    setSelectedCompetitors(competitorSeeds.slice(0, 2).map((item) => item.display_name));
  }, [competitorSeeds, selectedCompetitors.length]);

  const canSubmit =
    userQuery.trim().length > 0 &&
    selectedCompetitors.length > 0 &&
    !createRunMutation.isPending;

  function addCompetitor(rawValue: string): void {
    const value = rawValue.trim();
    if (!value) {
      return;
    }
    setSelectedCompetitors((prev) => {
      if (prev.includes(value)) {
        return prev;
      }
      return [...prev, value];
    });
    setCompetitorInput("");
  }

  function removeCompetitor(value: string): void {
    setSelectedCompetitors((prev) => {
      if (prev.length <= 1) {
        setShowCompetitorWarning(true);
        setTimeout(() => setShowCompetitorWarning(false), 3000);
        return prev;
      }
      return prev.filter((item) => item !== value);
    });
  }

  function addReferenceUrl(rawValue: string): void {
    const value = rawValue.trim();
    if (!value) {
      return;
    }
    setReferenceUrls((prev) => {
      if (prev.includes(value)) {
        return prev;
      }
      return [...prev, value];
    });
    setReferenceUrlInput("");
  }

  function removeReferenceUrl(value: string): void {
    setReferenceUrls((prev) => prev.filter((item) => item !== value));
  }

  function toggleRole(roleId: string): void {
    setTargetRoles((prev) => {
      if (prev.includes(roleId)) {
        return prev.filter((item) => item !== roleId);
      }
      return [...prev, roleId];
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    try {
      const created = await createRunMutation.mutateAsync({
        user_query: userQuery.trim(),
        competitors: selectedCompetitors,
        domain_hint: domainHint.trim() ? domainHint.trim() : null,
        reference_urls: referenceUrls.length > 0 ? referenceUrls : null,
        target_roles: targetRoles,
      });
      navigate(`/runs/${created.run_id}`);
    } catch (error) {
      console.error("Run creation failed:", error);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 grid-bg">
      <ParticleBackground />

      {/* Header */}
      <header className={`sticky top-0 z-50 glass border-b border-slate-100/50 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"}`}>
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => navigate("/")} 
              className="group text-slate-600 hover:text-slate-900 hover:bg-slate-100 h-10 w-10 p-0 rounded-xl transition-all duration-300 hover:scale-110"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div className="flex items-center gap-2 group cursor-pointer">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 group-hover:rotate-12">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg blur-md opacity-50 group-hover:opacity-75" />
              </div>
              <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
            </div>
            <div className="w-10" />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 relative z-10">
        {/* Hero Section */}
        <div className={`text-center mb-8 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
          <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 rounded-full text-white text-sm font-medium shadow-lg shadow-blue-500/25 mb-4 animate-pulse-glow">
            <Sparkles className="h-4 w-4" />
            创建新分析
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-slate-900 mb-3">
            <span className="gradient-text">新建分析任务</span>
          </h1>
          <p className="text-slate-600">
            填写分析问题与竞品后即可启动，Agent 将在运行时动态规划分析维度
          </p>
        </div>

        {/* Info Banner */}
        {competitorSeedsQuery.isError && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-xl animate-slide-up">
            <p className="text-sm text-blue-800">
              当前使用本地推荐的竞品列表。如需获取最新竞品数据，请联系管理员检查后端服务。
            </p>
          </div>
        )}

        {/* Card */}
        <Card className={`border-0 shadow-xl shadow-slate-100/50 overflow-hidden transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "100ms" }}>
          <CardHeader className="bg-gradient-to-r from-blue-500 via-purple-500 to-blue-600 animate-gradient-shift">
            <CardTitle className="text-lg text-white font-semibold">
              <Sparkles className="h-5 w-5 mr-2 inline" />
              任务参数配置
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 space-y-6">
            <form className="space-y-6" onSubmit={handleSubmit}>
              {/* Analysis Query */}
              <div className={`space-y-2 transition-all duration-300 ${focusedField === "query" ? "scale-[1.01]" : ""}`}>
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs">1</span>
                  分析问题 <span className="text-red-500">*</span>
                </label>
                <textarea
                  className="min-h-24 w-full rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-slate-800 text-sm outline-none transition-all duration-300 resize-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 hover:border-slate-300"
                  id="user-query"
                  onChange={(event) => setUserQuery(event.target.value)}
                  onFocus={() => setFocusedField("query")}
                  onBlur={() => setFocusedField(null)}
                  value={userQuery}
                  placeholder="输入您想要分析的问题，例如：AI Coding 工具竞争格局分析"
                />
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-500">作为分析任务的核心问题，将引导整个分析流程</p>
                  <span className={`text-xs font-medium transition-colors ${userQuery.trim().length > 0 ? "text-green-600" : "text-slate-400"}`}>
                    {userQuery.trim().length > 0 ? "✓ 已填写" : "请输入"}
                  </span>
                </div>
              </div>

              {/* Domain Hint */}
              <div className={`space-y-2 transition-all duration-300 ${focusedField === "domain" ? "scale-[1.01]" : ""}`}>
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center text-white text-xs">2</span>
                  领域提示（可选）
                </label>
                <textarea
                  className="min-h-20 w-full rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-slate-800 text-sm outline-none transition-all duration-300 resize-none focus:border-green-500 focus:ring-4 focus:ring-green-100 hover:border-slate-300"
                  id="domain-hint"
                  onChange={(event) => setDomainHint(event.target.value)}
                  onFocus={() => setFocusedField("domain")}
                  onBlur={() => setFocusedField(null)}
                  placeholder="例如：协作知识库产品、B2B SaaS、面向企业采购决策"
                  value={domainHint}
                />
                <p className="text-xs text-slate-500">作为运行时提示，帮助 Agent 更快选定信息源和维度</p>
              </div>

              {/* Competitors */}
              <div className={`space-y-3 transition-all duration-300 ${focusedField === "competitor" ? "scale-[1.01]" : ""}`}>
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center text-white text-xs">3</span>
                    竞品 <span className="text-red-500">*</span>
                  </label>
                  <span className="text-xs text-slate-500">自动补全 + 自由输入</span>
                </div>
                <div className="flex gap-2">
                  <input
                    className="h-11 flex-1 rounded-xl border-2 border-slate-200 bg-white px-4 text-slate-800 text-sm outline-none transition-all duration-300 focus:border-purple-500 focus:ring-4 focus:ring-purple-100 hover:border-slate-300"
                    onChange={(event) => setCompetitorInput(event.target.value)}
                    onFocus={() => setFocusedField("competitor")}
                    onBlur={() => setFocusedField(null)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") {
                        return;
                      }
                      event.preventDefault();
                      addCompetitor(competitorInput);
                    }}
                    placeholder="输入竞品名，例如 Notion / Obsidian"
                    value={competitorInput}
                  />
                  <Button 
                    onClick={() => addCompetitor(competitorInput)} 
                    type="button" 
                    variant="outline"
                    className="border-2 border-slate-300 text-slate-700 hover:bg-purple-50 hover:border-purple-400 rounded-xl transition-all duration-300 hover:scale-105"
                    disabled={!competitorInput.trim()}
                  >
                    <PlusIcon />
                  </Button>
                </div>
                {competitorSuggestions.length > 0 && competitorInput.trim() === "" && (
                  <div className="flex flex-wrap gap-2 animate-slide-up">
                    {competitorSuggestions.map((item, index) => (
                      <button
                        key={item.id}
                        onClick={() => addCompetitor(item.display_name)}
                        type="button"
                        className="group relative rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-purple-50 hover:border-purple-300 transition-all duration-300 hover:scale-105"
                        style={{ animationDelay: `${index * 50}ms` }}
                      >
                        <span className="relative z-10">{item.display_name}</span>
                        <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  {selectedCompetitors.map((item, index) => (
                    <button
                      key={item}
                      onClick={() => removeCompetitor(item)}
                      type="button"
                      className="group flex items-center gap-1.5 rounded-lg border-2 border-blue-500 bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100 hover:scale-105 transition-all duration-300"
                      style={{ animationDelay: `${index * 50}ms` }}
                    >
                      <Check className="h-3 w-3 text-blue-600" />
                      {item}
                      <X className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>
                {showCompetitorWarning && (
                  <div className="mt-2 p-3 bg-amber-50 border-2 border-amber-300 rounded-xl animate-scale-in">
                    <p className="text-sm text-amber-700 flex items-center gap-2">
                      <AlertIcon />
                      请至少选择一个竞品进行分析
                    </p>
                  </div>
                )}
              </div>

              {/* Reference URLs */}
              <div className={`space-y-3 transition-all duration-300 ${focusedField === "url" ? "scale-[1.01]" : ""}`}>
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white text-xs">4</span>
                  参考 URL（可选）
                </label>
                <div className="flex gap-2">
                  <input
                    className="h-11 flex-1 rounded-xl border-2 border-slate-200 bg-white px-4 text-slate-800 text-sm outline-none transition-all duration-300 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100 hover:border-slate-300"
                    onChange={(event) => setReferenceUrlInput(event.target.value)}
                    onFocus={() => setFocusedField("url")}
                    onBlur={() => setFocusedField(null)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") {
                        return;
                      }
                      event.preventDefault();
                      addReferenceUrl(referenceUrlInput);
                    }}
                    placeholder="https://..."
                    value={referenceUrlInput}
                  />
                  <Button 
                    onClick={() => addReferenceUrl(referenceUrlInput)} 
                    type="button" 
                    variant="outline"
                    className="border-2 border-slate-300 text-slate-700 hover:bg-cyan-50 hover:border-cyan-400 rounded-xl transition-all duration-300 hover:scale-105"
                    disabled={!referenceUrlInput.trim()}
                  >
                    <PlusIcon />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {referenceUrls.map((item, index) => (
                    <button
                      key={item}
                      onClick={() => removeReferenceUrl(item)}
                      type="button"
                      className="group flex items-center gap-1 rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-red-50 hover:border-red-300 transition-all duration-300 hover:scale-105"
                      style={{ animationDelay: `${index * 50}ms` }}
                    >
                      <ExternalLinkIcon />
                      {item.length > 30 ? item.slice(0, 30) + "..." : item}
                      <X className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>
              </div>

              {/* Target Roles */}
              <div className="space-y-3">
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center text-white text-xs">5</span>
                  关注角色
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {ROLE_OPTIONS.map((role) => (
                    <button
                      key={role.id}
                      onClick={() => toggleRole(role.id)}
                      type="button"
                      className={`group relative flex items-center justify-center gap-2 rounded-xl border-2 px-4 py-3 text-sm transition-all duration-300 ${
                        targetRoles.includes(role.id)
                          ? "border-orange-500 bg-orange-50 text-orange-700"
                          : "border-slate-200 text-slate-600 hover:border-orange-300 hover:bg-orange-50/50"
                      }`}
                    >
                      <role.icon className={`h-4 w-4 transition-transform ${targetRoles.includes(role.id) ? "group-hover:scale-110" : ""}`} />
                      <span>{role.label}</span>
                      {targetRoles.includes(role.id) && (
                        <Check className="absolute top-2 right-2 h-3 w-3 text-orange-600" />
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Error Message */}
              {createRunMutation.isError && (
                <div className="p-4 bg-red-50 border-2 border-red-300 rounded-xl animate-scale-in">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center flex-shrink-0">
                      <AlertCircle className="h-5 w-5 text-red-600" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-red-800">分析任务创建失败</p>
                      <p className="text-xs text-red-600 mt-1">
                        {createRunMutation.error.message || "服务器内部错误，请稍后重试"}
                      </p>
                      <p className="text-xs text-red-600 mt-2">
                        任务可能已部分创建，您可以返回首页查看任务列表。
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Submit Button */}
              <div className="flex justify-center pt-6">
                <Button 
                  disabled={!canSubmit} 
                  type="submit"
                  size="lg"
                  className="group relative overflow-hidden bg-gradient-to-r from-blue-600 via-purple-600 to-blue-700 hover:from-blue-700 hover:via-purple-700 hover:to-blue-800 text-white px-12 py-7 text-lg font-semibold shadow-xl shadow-blue-600/30 transition-all duration-300 hover:shadow-2xl hover:shadow-blue-600/40 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
                >
                  <span className="relative z-10 flex items-center">
                    {createRunMutation.isPending ? (
                      <>
                        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                        启动中...
                      </>
                    ) : (
                      <>
                        <Zap className="h-5 w-5 mr-2" />
                        启动分析
                      </>
                    )}
                  </span>
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

// Helper icons
function PlusIcon(): JSX.Element {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  );
}

function AlertIcon(): JSX.Element {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}

function ExternalLinkIcon(): JSX.Element {
  return (
    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

