import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Zap,
  AlertTriangle,
  RotateCcw,
  CheckCircle2,
  Clock,
  ArrowRight,
  Eye,
  Search,
  Filter,
  ChevronRight,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

interface FeedbackRecord {
  run_id: string;
  step_id: string;
  agent_name: string;
  status: string;
  retry_count: number;
  rejection_reason: string | null;
  rejected_at: string;
  last_retry_at: string | null;
}

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
      speedX: (Math.random() - 0.5) * 0.15,
      speedY: (Math.random() - 0.5) * 0.15,
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
          className="absolute rounded-full bg-gradient-to-br from-red-500/30 to-orange-500/30 animate-breathe"
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

const AGENT_ROLES: Record<string, string> = {
  supervisor: "任务调度",
  researcher: "信息采集",
  analyst: "竞品分析",
  writer: "报告撰写",
  qa: "质量校验",
  skill_curator: "技能沉淀",
};

const STATUS_COLORS: Record<string, string> = {
  rejected: "bg-red-500/10 text-red-400 border-red-500/20",
  retried: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  resolved: "bg-green-500/10 text-green-400 border-green-500/20",
  pending: "bg-blue-500/10 text-blue-400 border-blue-500/20",
};

const STATUS_LABELS: Record<string, string> = {
  rejected: "已拒绝",
  retried: "重试中",
  resolved: "已解决",
  pending: "待处理",
};

// Mock data for feedback loop records
const mockFeedbackRecords: FeedbackRecord[] = [
  {
    run_id: "run-abc123",
    step_id: "step-001",
    agent_name: "researcher",
    status: "retried",
    retry_count: 2,
    rejection_reason: "证据来源可信度不足，请补充更多权威来源",
    rejected_at: "2026-06-01T10:30:00Z",
    last_retry_at: "2026-06-01T11:15:00Z",
  },
  {
    run_id: "run-def456",
    step_id: "step-002",
    agent_name: "writer",
    status: "resolved",
    retry_count: 1,
    rejection_reason: "报告结论与证据不符，需要重新核对",
    rejected_at: "2026-06-01T09:00:00Z",
    last_retry_at: "2026-06-01T09:45:00Z",
  },
  {
    run_id: "run-ghi789",
    step_id: "step-003",
    agent_name: "analyst",
    status: "rejected",
    retry_count: 0,
    rejection_reason: "SWOT分析逻辑不清晰，缺少竞品对比维度",
    rejected_at: "2026-06-01T14:20:00Z",
    last_retry_at: null,
  },
  {
    run_id: "run-jkl012",
    step_id: "step-004",
    agent_name: "writer",
    status: "pending",
    retry_count: 0,
    rejection_reason: "定价模型分析不够深入，建议增加市场份额数据",
    rejected_at: "2026-06-01T15:00:00Z",
    last_retry_at: null,
  },
  {
    run_id: "run-mno345",
    step_id: "step-005",
    agent_name: "researcher",
    status: "retried",
    retry_count: 3,
    rejection_reason: "用户访谈记录不完整，关键问题未覆盖",
    rejected_at: "2026-05-31T16:30:00Z",
    last_retry_at: "2026-06-01T08:00:00Z",
  },
];

export function FeedbackLoopPage(): JSX.Element {
  const navigate = useNavigate();
  const [isVisible, setIsVisible] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [selectedRecord, setSelectedRecord] = useState<FeedbackRecord | null>(null);

  useEffect(() => {
    setIsVisible(true);
  }, []);

  const filteredRecords = mockFeedbackRecords.filter((record) => {
    const matchesSearch =
      record.run_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      record.rejection_reason?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFilter = filterStatus === "all" || record.status === filterStatus;
    return matchesSearch && matchesFilter;
  });

  const stats = {
    total: mockFeedbackRecords.length,
    rejected: mockFeedbackRecords.filter((r) => r.status === "rejected").length,
    retried: mockFeedbackRecords.filter((r) => r.status === "retried").length,
    resolved: mockFeedbackRecords.filter((r) => r.status === "resolved").length,
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 relative">
      <ParticleBackground />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(239,68,68,0.05),transparent_70%)]" />

      {/* Header */}
      <header
        className={`sticky top-0 z-50 bg-slate-900/80 backdrop-blur-sm border-b border-slate-700 transition-all duration-500 ${
          isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"
        }`}
      >
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-red-500 to-orange-600 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 group-hover:rotate-12">
                  <AlertTriangle className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-red-500 to-orange-600 rounded-lg blur-md opacity-50 group-hover:opacity-75" />
              </div>
              <span className="font-semibold text-white">RivalLens</span>
            </Link>

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
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                监控仪表盘
              </Link>
              <Link
                to="/feedback"
                className="px-4 py-2 rounded-lg text-sm font-medium bg-red-500/10 text-red-400 relative"
              >
                反馈闭环
                <span className="absolute inset-0 bg-gradient-to-r from-red-500/10 to-orange-500/10 rounded-lg animate-pulse-glow" />
              </Link>
              <Link
                to="/skills/staging"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-white transition-all"
              >
                Skill 审核台
              </Link>
            </nav>

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => navigate("/runs/new")}
                className="group relative overflow-hidden bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700 text-white"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-4 w-4 mr-1" />
                  开始分析
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-red-400 to-orange-500 opacity-0 group-hover:opacity-100 transition-opacity" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8 relative z-10">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-red-500 to-orange-600 flex items-center justify-center">
                  <RotateCcw className="h-5 w-5 text-white" />
                </div>
                反馈闭环管理
              </h1>
              <p className="text-slate-400 mt-1">追踪QA质检Agent打回的任务，监控闭环处理进度</p>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-4 gap-4">
            <Card className="bg-slate-800/50 border-slate-700 hover:border-slate-600 transition-all">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-slate-400 text-sm">总反馈记录</p>
                    <p className="text-2xl font-bold text-white mt-1">{stats.total}</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-slate-700/50 flex items-center justify-center">
                    <AlertTriangle className="h-5 w-5 text-orange-400" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-slate-800/50 border-slate-700 hover:border-red-500/30 transition-all">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-slate-400 text-sm">待处理</p>
                    <p className="text-2xl font-bold text-red-400 mt-1">{stats.rejected}</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                    <Clock className="h-5 w-5 text-red-400" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-slate-800/50 border-slate-700 hover:border-amber-500/30 transition-all">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-slate-400 text-sm">重试中</p>
                    <p className="text-2xl font-bold text-amber-400 mt-1">{stats.retried}</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                    <RotateCcw className="h-5 w-5 text-amber-400" />
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card className="bg-slate-800/50 border-slate-700 hover:border-green-500/30 transition-all">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-slate-400 text-sm">已解决</p>
                    <p className="text-2xl font-bold text-green-400 mt-1">{stats.resolved}</p>
                  </div>
                  <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                    <CheckCircle2 className="h-5 w-5 text-green-400" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center gap-4 mb-6">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <Input
              type="text"
              placeholder="搜索任务ID或拒绝原因..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-slate-800 border-slate-700 text-white placeholder:text-slate-500 focus:border-red-500/50"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-500" />
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-red-500/50"
            >
              <option value="all">全部状态</option>
              <option value="rejected">已拒绝</option>
              <option value="retried">重试中</option>
              <option value="resolved">已解决</option>
              <option value="pending">待处理</option>
            </select>
          </div>
        </div>

        {/* Feedback List */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredRecords.length === 0 ? (
            <div className="col-span-2 text-center py-16">
              <div className="w-16 h-16 rounded-full bg-slate-800 mx-auto mb-4 flex items-center justify-center">
                <CheckCircle2 className="h-8 w-8 text-slate-600" />
              </div>
              <p className="text-slate-400">暂无反馈记录</p>
            </div>
          ) : (
            filteredRecords.map((record) => (
              <Card
                key={`${record.run_id}-${record.step_id}`}
                className={`bg-slate-800/50 border-slate-700 hover:border-red-500/30 transition-all cursor-pointer ${
                  selectedRecord?.run_id === record.run_id ? "ring-2 ring-red-500/50" : ""
                }`}
                onClick={() => setSelectedRecord(record)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${AGENT_COLORS[record.agent_name]} flex items-center justify-center`}>
                        <Zap className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-white font-medium">{AGENT_ROLES[record.agent_name]}</p>
                        <p className="text-slate-500 text-sm font-mono">{record.run_id}</p>
                      </div>
                    </div>
                    <Badge className={STATUS_COLORS[record.status]}>{STATUS_LABELS[record.status]}</Badge>
                  </div>

                  <div className="mb-3">
                    <p className="text-slate-300 text-sm leading-relaxed">
                      <span className="text-red-400 font-medium">拒绝原因：</span>
                      {record.rejection_reason}
                    </p>
                  </div>

                  <div className="flex items-center justify-between text-sm text-slate-500">
                    <div className="flex items-center gap-4">
                      <span className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        {formatDate(record.rejected_at)}
                      </span>
                      <span className="flex items-center gap-1">
                        <RotateCcw className="h-4 w-4" />
                        重试 {record.retry_count} 次
                      </span>
                    </div>
                    <ChevronRight className="h-4 w-4 text-slate-600" />
                  </div>

                  {record.last_retry_at && (
                    <div className="mt-3 pt-3 border-t border-slate-700">
                      <p className="text-xs text-slate-500">
                        最后重试时间：{formatDate(record.last_retry_at)}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Detail Panel */}
        {selectedRecord && (
          <Card className="mt-6 bg-slate-800/70 border-slate-700">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <Eye className="h-5 w-5 text-red-400" />
                反馈详情
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-slate-400 text-xs">任务ID</p>
                  <p className="text-white font-mono text-sm mt-1">{selectedRecord.run_id}</p>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-slate-400 text-xs">Agent</p>
                  <p className="text-white mt-1">{AGENT_ROLES[selectedRecord.agent_name]}</p>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-slate-400 text-xs">状态</p>
                  <Badge className={STATUS_COLORS[selectedRecord.status]} mt-1>
                    {STATUS_LABELS[selectedRecord.status]}
                  </Badge>
                </div>
                <div className="bg-slate-700/50 rounded-lg p-4">
                  <p className="text-slate-400 text-xs">重试次数</p>
                  <p className="text-white mt-1">{selectedRecord.retry_count} 次</p>
                </div>
              </div>

              <div className="mb-6">
                <p className="text-slate-400 text-sm mb-2">拒绝原因</p>
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
                  <p className="text-red-300">{selectedRecord.rejection_reason}</p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                  onClick={() => navigate(`/runs/${selectedRecord.run_id}`)}
                >
                  <Eye className="h-4 w-4 mr-2" />
                  查看任务详情
                </Button>
                <Button
                  variant="outline"
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                  onClick={() => navigate(`/runs/${selectedRecord.run_id}/trace`)}
                >
                  <ArrowRight className="h-4 w-4 mr-2" />
                  查看执行轨迹
                </Button>
                {selectedRecord.status === "rejected" && (
                  <Button className="bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700">
                    <RotateCcw className="h-4 w-4 mr-2" />
                    触发重试
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-12 py-8">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-slate-500 text-sm">
            RivalLens - AI驱动的竞品分析Agent协作系统
          </p>
        </div>
      </footer>
    </div>
  );
}
