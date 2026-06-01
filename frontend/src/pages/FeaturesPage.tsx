import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Brain, Target, TrendingUp, Lightbulb, CheckCircle2, Sparkles, Zap, Shield, BarChart3, FileText, Users, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

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
      size: Math.random() * 3 + 1,
      speedX: (Math.random() - 0.5) * 0.3,
      speedY: (Math.random() - 0.5) * 0.3,
      opacity: Math.random() * 0.4 + 0.1,
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
    }, 60);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute rounded-full bg-gradient-to-br from-blue-500/50 to-purple-600/50 animate-breathe"
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

function AnimatedCounter({ target, duration = 1000, suffix = "" }: { target: number; duration?: number; suffix?: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.5 }
    );

    if (ref.current) {
      observer.observe(ref.current);
    }

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isVisible) return;

    let startTime: number | null = null;
    const animate = (currentTime: number) => {
      if (!startTime) startTime = currentTime;
      const progress = Math.min((currentTime - startTime) / duration, 1);
      setCount(Math.floor(progress * target));
      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };
    requestAnimationFrame(animate);
  }, [target, duration, isVisible]);

  return (
    <span ref={ref} className="font-bold">
      {count}{suffix}
    </span>
  );
}

export function FeaturesPage(): JSX.Element {
  const navigate = useNavigate();
  const [isVisible, setIsVisible] = useState(false);
  const [animatedFeatures, setAnimatedFeatures] = useState<boolean[]>([]);

  useEffect(() => {
    setIsVisible(true);
    setAnimatedFeatures(new Array(6).fill(false));
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = parseInt(entry.target.getAttribute("data-index") || "0");
            setAnimatedFeatures((prev) => {
              const newArr = [...prev];
              newArr[index] = true;
              return newArr;
            });
          }
        });
      },
      { threshold: 0.2 }
    );

    document.querySelectorAll("[data-index]").forEach((el) => {
      observer.observe(el);
    });

    return () => observer.disconnect();
  }, []);

  const features = [
    {
      icon: Brain,
      title: "智能调度引擎",
      description: "基于 LangGraph 的多 Agent 协作框架，自动规划分析流程，动态分配任务给最适合的 Agent 执行",
      color: "from-blue-500 to-blue-600",
      stats: "6",
      statsLabel: "专职 Agent",
    },
    {
      icon: Target,
      title: "深度信息采集",
      description: "智能爬虫技术，自动收集竞品官网、应用商店、社交媒体等多渠道信息，构建完整的竞品画像",
      color: "from-green-500 to-green-600",
      stats: "50+",
      statsLabel: "信息源",
    },
    {
      icon: TrendingUp,
      title: "跨维度分析",
      description: "支持功能对比、市场定位、用户评价、技术架构等多维度深度分析，挖掘竞争机会",
      color: "from-purple-500 to-purple-600",
      stats: "10+",
      statsLabel: "分析维度",
    },
    {
      icon: Lightbulb,
      title: "智能报告生成",
      description: "基于分析结果自动撰写专业的 Battlecard 报告，包含数据表格、对比图表和战略建议",
      color: "from-orange-500 to-orange-600",
      stats: "98%",
      statsLabel: "报告质量",
    },
    {
      icon: CheckCircle2,
      title: "质量保证体系",
      description: "多轮 QA 校验机制，确保分析结果的准确性和可靠性，支持证据溯源验证",
      color: "from-cyan-500 to-cyan-600",
      stats: "3",
      statsLabel: "轮 QA 校验",
    },
    {
      icon: Shield,
      title: "企业级安全",
      description: "端到端加密传输，严格的数据访问控制，支持私有化部署，保护商业机密",
      color: "from-indigo-500 to-indigo-600",
      stats: "256",
      statsLabel: "位加密",
    },
  ];

  const useCases = [
    {
      title: "产品经理",
      desc: "快速了解竞品功能特性，制定产品迭代策略",
      icon: BarChart3,
    },
    {
      title: "创业者",
      desc: "分析市场竞争格局，发现差异化切入点",
      icon: Target,
    },
    {
      title: "投资人",
      desc: "全面评估竞品价值，辅助投资决策",
      icon: FileText,
    },
    {
      title: "销售团队",
      desc: "获取竞品弱点情报，提升销售话术竞争力",
      icon: Users,
    },
  ];

  const comparisons = [
    { feature: "分析维度", manual: "有限", ai: "50+ 维度" },
    { feature: "分析周期", manual: "数天", ai: "5 分钟" },
    { feature: "数据来源", manual: "单一", ai: "多渠道整合" },
    { feature: "报告质量", manual: "参差不齐", ai: "标准化专业报告" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 grid-bg">
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
                className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-50 text-blue-600 relative"
              >
                功能介绍
                <span className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-lg animate-pulse-glow" />
              </Link>
              <Link
                to="/runs"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                任务列表
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

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-16 px-4">
        <div className="absolute top-20 right-10 w-80 h-80 bg-gradient-to-br from-blue-400/20 to-purple-400/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 left-10 w-64 h-64 bg-gradient-to-br from-cyan-400/20 to-blue-400/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />
        
        <div className="relative max-w-4xl mx-auto text-center">
          <div className={`inline-flex items-center gap-2 px-4 py-2 mb-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-full text-white text-sm font-medium shadow-lg shadow-blue-500/25 transition-all duration-500 ${isVisible ? "opacity-100 scale-100" : "opacity-0 scale-90"}`}>
            <Sparkles className="h-4 w-4 animate-spin-slow" />
            功能介绍
          </div>
          
          <h1 className={`text-4xl md:text-5xl font-bold text-slate-900 mb-6 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}>
            <span className="gradient-text glow-text">重新定义竞品分析</span>
          </h1>
          
          <p className={`text-xl text-slate-600 max-w-2xl mx-auto mb-12 transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "200ms" }}>
            将传统耗时费力的竞品分析工作，转化为高效、精准、自动化的智能流程
          </p>

          {/* Stats */}
          <div className={`grid grid-cols-2 md:grid-cols-4 gap-6 max-w-2xl mx-auto transition-all duration-700 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`} style={{ transitionDelay: "400ms" }}>
            {[
              { value: 50, suffix: "+", label: "分析维度" },
              { value: 5, suffix: "分钟", label: "平均耗时" },
              { value: 98, suffix: "%", label: "报告质量" },
              { value: 6, suffix: "", label: "专职 Agent" },
            ].map((stat, index) => (
              <div 
                key={stat.label}
                className="text-center p-4 rounded-xl bg-white/60 backdrop-blur-sm border border-slate-100/50 hover-lift"
                style={{ animationDelay: `${500 + index * 100}ms` }}
              >
                <div className="text-3xl font-bold gradient-text mb-1">
                  <AnimatedCounter target={stat.value} suffix={stat.suffix} />
                </div>
                <div className="text-sm text-slate-500">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-16 px-4 bg-white relative">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-blue-50/30 to-transparent" />
        
        <div className="max-w-6xl mx-auto relative">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-slate-900 mb-4 gradient-text">核心功能能力</h2>
            <p className="text-slate-600">全方位的智能分析能力，满足不同场景的竞品分析需求</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, index) => (
              <Card 
                key={feature.title}
                data-index={index}
                className={`group relative border-0 bg-white shadow-lg shadow-slate-100/50 overflow-hidden transition-all duration-500 hover-lift ${animatedFeatures[index] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
                style={{ transitionDelay: `${index * 100}ms` }}
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className={`relative w-14 h-14 bg-gradient-to-br ${feature.color} rounded-xl flex items-center justify-center text-white shadow-lg group-hover:scale-110 transition-transform duration-300`}>
                      <feature.icon className="h-7 w-7" />
                      <div className={`absolute inset-0 bg-gradient-to-br ${feature.color} rounded-xl blur-md opacity-0 group-hover:opacity-50 transition-opacity`} />
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold gradient-text">{feature.stats}</div>
                      <div className="text-xs text-slate-500">{feature.statsLabel}</div>
                    </div>
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 mb-2 group-hover:text-blue-600 transition-colors">{feature.title}</h3>
                  <p className="text-sm text-slate-600 leading-relaxed">{feature.description}</p>
                  
                  {/* Hover decoration */}
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity transform scale-x-0 group-hover:scale-x-100" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison Section */}
      <section className="py-16 px-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 animate-gradient-shift" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.1),transparent_70%)]" />
        
        <div className="max-w-3xl mx-auto relative z-10">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-white mb-4">
              <Sparkles className="h-6 w-6 inline mr-2 text-blue-400" />
              AI vs 传统方式
            </h2>
            <p className="text-slate-400">效率与质量的全面超越</p>
          </div>
          
          <div className="relative bg-slate-800/80 backdrop-blur-sm rounded-2xl border border-slate-700/50 overflow-hidden shadow-2xl">
            {/* Glow effect */}
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/5 via-purple-500/5 to-blue-500/5 animate-gradient-shift" />
            
            <div className="relative z-10">
              <div className="grid grid-cols-3 gap-4 p-6 bg-slate-800/80 border-b border-slate-700/50">
                <div className="text-center">
                  <p className="text-slate-400 text-sm font-medium">对比项</p>
                </div>
                <div className="text-center">
                  <p className="text-slate-400 text-sm font-medium">传统方式</p>
                </div>
                <div className="text-center">
                  <p className="text-blue-400 text-sm font-semibold flex items-center justify-center gap-1">
                    <Zap className="h-4 w-4" />
                    RivalLens
                  </p>
                </div>
              </div>
              
              {comparisons.map((item, index) => (
                <div 
                  key={item.feature}
                  className={`grid grid-cols-3 gap-4 p-5 border-t border-slate-700/30 hover:bg-slate-700/30 transition-colors ${index % 2 === 0 ? "" : "bg-slate-800/30"}`}
                >
                  <div className="text-center">
                    <p className="text-white font-medium">{item.feature}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-slate-400">{item.manual}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-green-400 font-semibold flex items-center justify-center">
                      <CheckCircle2 className="h-4 w-4 mr-1" />
                      {item.ai}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-slate-900 mb-4 gradient-text">适用人群</h2>
            <p className="text-slate-600">无论您是什么角色，都能从中受益</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {useCases.map((item, index) => (
              <div 
                key={item.title}
                className={`group flex items-center gap-4 p-6 rounded-2xl border border-slate-100 hover:border-blue-200 transition-all duration-300 hover-lift cursor-pointer ${index % 2 === 0 ? "bg-gradient-to-r from-blue-50/50 to-white" : "bg-gradient-to-r from-purple-50/50 to-white"}`}
              >
                <div className="relative w-14 h-14 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center text-white flex-shrink-0 group-hover:scale-110 transition-transform">
                  <item.icon className="h-6 w-6" />
                  <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl blur-md opacity-0 group-hover:opacity-50 transition-opacity" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-slate-900 mb-1 group-hover:text-blue-600 transition-colors">{item.title}</h3>
                  <p className="text-sm text-slate-600">{item.desc}</p>
                </div>
                <ArrowRight className="h-5 w-5 text-slate-300 group-hover:text-blue-500 group-hover:translate-x-1 transition-all" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 px-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-purple-600 to-blue-700 animate-gradient-shift" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.1),transparent_70%)]" />
        
        <div className="max-w-3xl mx-auto text-center relative z-10">
          <div className={`inline-flex items-center gap-2 px-4 py-2 mb-6 bg-white/10 backdrop-blur-sm rounded-full text-white text-sm font-medium transition-all duration-500 ${isVisible ? "opacity-100 scale-100" : "opacity-0 scale-90"}`}>
            <Zap className="h-4 w-4" />
            立即体验
          </div>
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4 glow-text">准备好体验智能竞品分析了吗？</h2>
          <p className="text-blue-100 mb-8 text-lg">
            立即创建您的第一个分析任务，体验 AI 带来的效率革命
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button 
              size="lg"
              className="group relative overflow-hidden bg-white text-blue-600 hover:bg-blue-50 px-10 py-7 text-lg font-semibold shadow-xl transition-all hover:shadow-2xl hover:scale-105"
              onClick={() => navigate("/runs/new")}
            >
              <span className="relative z-10 flex items-center">
                <Zap className="h-5 w-5 mr-2" />
                开始新分析
              </span>
              <div className="absolute inset-0 bg-gradient-to-r from-blue-100 to-purple-100 opacity-0 group-hover:opacity-100 transition-opacity" />
            </Button>
            <Button 
              size="lg"
              className="group relative overflow-hidden bg-white/10 backdrop-blur-sm border-2 border-white/30 text-white hover:bg-white/20 px-10 py-7 text-lg font-semibold transition-all"
              onClick={() => navigate("/")}
            >
              <span className="relative z-10 flex items-center">
                返回首页
                <ArrowRight className="h-5 w-5 ml-2 group-hover:translate-x-1 transition-transform" />
              </span>
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white border-t border-slate-100">
        <div className="max-w-5xl mx-auto text-center">
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
