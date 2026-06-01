import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText, Download, Link2, Copy, Check, Eye, Clock, Lock, Unlock } from "lucide-react";

import { useRunDetail, useRunReport } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

interface ExportFormat {
  id: string;
  name: string;
  icon: React.ReactNode;
  description: string;
  supported: boolean;
}

interface ReportVersion {
  id: string;
  version: string;
  date: string;
  changes: string[];
}

export function ReportExportPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const runId = runIdFromParams ?? "";
  const [copied, setCopied] = useState(false);
  const [visibility, setVisibility] = useState<"public" | "private">("private");
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);

  const detailQuery = useRunDetail(runId);
  const reportQuery = useRunReport(runId);

  const exportFormats: ExportFormat[] = [
    {
      id: "pdf",
      name: "PDF",
      icon: <FileText className="h-6 w-6" />,
      description: "专业格式，适合打印和分享",
      supported: true,
    },
    {
      id: "docx",
      name: "Word",
      icon: <FileText className="h-6 w-6" />,
      description: "可编辑文档，方便二次修改",
      supported: true,
    },
    {
      id: "md",
      name: "Markdown",
      icon: <FileText className="h-6 w-6" />,
      description: "纯文本格式，便于版本控制",
      supported: true,
    },
    {
      id: "json",
      name: "JSON",
      icon: <FileText className="h-6 w-6" />,
      description: "结构化数据，便于程序处理",
      supported: true,
    },
  ];

  const mockVersions: ReportVersion[] = [
    {
      id: "v3",
      version: "v1.3.0",
      date: "2024-01-25 16:30",
      changes: ["更新竞品C的定价信息", "添加SWOT分析内容", "优化报告格式"],
    },
    {
      id: "v2",
      version: "v1.2.0",
      date: "2024-01-24 14:20",
      changes: ["补充竞品B的用户评价", "添加市场份额数据", "修复报告排版问题"],
    },
    {
      id: "v1",
      version: "v1.1.0",
      date: "2024-01-23 10:15",
      changes: ["初始版本发布", "包含三个竞品的基础分析"],
    },
  ];

  const shareLink = `https://rivallens.example.com/share/${runId}`;

  async function copyLink(): Promise<void> {
    await navigator.clipboard.writeText(shareLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

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
                <h1 className="text-lg font-semibold text-slate-900">报告导出与分享</h1>
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
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Export Options */}
            <Card className="border-0 shadow-md">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Download className="h-5 w-5" />
                  导出报告
                </CardTitle>
                <p className="text-sm text-slate-500">选择您需要的导出格式</p>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {exportFormats.map((format) => (
                    <Button
                      key={format.id}
                      variant={format.supported ? "outline" : "ghost"}
                      className={cn(
                        "flex-col items-center gap-2 p-4 h-auto",
                        !format.supported && "opacity-50 cursor-not-allowed",
                      )}
                      disabled={!format.supported}
                    >
                      <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center text-blue-600">
                        {format.icon}
                      </div>
                      <span className="font-medium">{format.name}</span>
                      <span className="text-xs text-slate-500">{format.description}</span>
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Share Settings */}
            <Card className="border-0 shadow-md">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Link2 className="h-5 w-5" />
                  分享设置
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Share Link */}
                <div className="p-4 bg-slate-50 rounded-xl">
                  <div className="flex items-center gap-2 mb-2">
                    <Eye className="h-4 w-4 text-slate-500" />
                    <span className="text-sm font-medium text-slate-700">分享链接</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={shareLink}
                      readOnly
                      className="flex-1 px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm font-mono text-slate-700 outline-none"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={copyLink}
                      className="gap-2 border-slate-300"
                    >
                      {copied ? (
                        <>
                          <Check className="h-4 w-4 text-green-600" />
                          已复制
                        </>
                      ) : (
                        <>
                          <Copy className="h-4 w-4" />
                          复制
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Visibility Toggle */}
                <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl">
                  <div className="flex items-center gap-2">
                    {visibility === "public" ? (
                      <Unlock className="h-5 w-5 text-green-600" />
                    ) : (
                      <Lock className="h-5 w-5 text-slate-500" />
                    )}
                    <div>
                      <p className="text-sm font-medium text-slate-700">
                        {visibility === "public" ? "公开分享" : "私密分享"}
                      </p>
                      <p className="text-xs text-slate-500">
                        {visibility === "public" ? "任何人都可以访问此链接" : "仅授权用户可以访问"}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant={visibility === "public" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setVisibility(visibility === "public" ? "private" : "public")}
                    className={visibility === "public" ? "bg-green-600 hover:bg-green-700" : "border-slate-300"}
                  >
                    {visibility === "public" ? "设为私密" : "设为公开"}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Version History */}
            <Card className="border-0 shadow-md">
              <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                  <Clock className="h-5 w-5" />
                  版本历史
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {mockVersions.map((version) => (
                  <div
                    key={version.id}
                    className={cn(
                      "border rounded-xl overflow-hidden transition-all",
                      expandedVersion === version.id ? "border-blue-300" : "border-slate-200",
                    )}
                  >
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-50"
                      onClick={() => setExpandedVersion(expandedVersion === version.id ? null : version.id)}
                    >
                      <div className="flex items-center gap-3">
                        <span className="px-3 py-1 text-sm font-medium bg-blue-100 text-blue-700 rounded-full">
                          {version.version}
                        </span>
                        <span className="text-sm text-slate-600">{version.date}</span>
                      </div>
                      <Button variant="outline" size="sm" className="gap-2 border-slate-300">
                        <Download className="h-4 w-4" />
                        下载
                      </Button>
                    </div>
                    {expandedVersion === version.id && (
                      <div className="px-4 pb-4">
                        <p className="text-xs text-slate-500 mb-2">更新内容：</p>
                        <ul className="space-y-1">
                          {version.changes.map((change, index) => (
                            <li key={index} className="text-sm text-slate-600 flex items-center gap-2">
                              <Check className="h-4 w-4 text-green-600" />
                              {change}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
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