import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCompetitorSeeds, useCreateRun } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ROLE_OPTIONS: Array<{ id: string; label: string }> = [
  { id: "pm", label: "产品经理" },
  { id: "founder", label: "创业者" },
  { id: "sales", label: "销售" },
  { id: "investor", label: "投资人" },
];

export function NewRunPage(): JSX.Element {
  const navigate = useNavigate();
  const competitorSeedsQuery = useCompetitorSeeds();
  const createRunMutation = useCreateRun();

  const [userQuery, setUserQuery] = useState("AI Coding 工具竞争格局分析");
  const [domainHint, setDomainHint] = useState("");
  const [competitorInput, setCompetitorInput] = useState("");
  const [selectedCompetitors, setSelectedCompetitors] = useState<string[]>([]);
  const [referenceUrlInput, setReferenceUrlInput] = useState("");
  const [referenceUrls, setReferenceUrls] = useState<string[]>([]);
  const [targetRoles, setTargetRoles] = useState<string[]>(["pm", "founder"]);

  const competitorSeeds = competitorSeedsQuery.data ?? [];
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
    if (competitorSeeds.length === 0 || selectedCompetitors.length > 0) {
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
    setSelectedCompetitors((prev) => prev.filter((item) => item !== value));
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
    const created = await createRunMutation.mutateAsync({
      user_query: userQuery.trim(),
      competitors: selectedCompetitors,
      domain_hint: domainHint.trim() ? domainHint.trim() : null,
      reference_urls: referenceUrls.length > 0 ? referenceUrls : null,
      target_roles: targetRoles,
    });
    navigate(`/runs/${created.run_id}`);
  }

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">新建分析任务</h1>
        <p className="text-sm text-muted-foreground">填写分析问题与竞品后即可启动，Agent 将在运行时动态规划分析维度。</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">任务参数</CardTitle>
        </CardHeader>
        <CardContent>
          {competitorSeedsQuery.isLoading ? <p className="text-sm text-muted-foreground">竞品样例加载中...</p> : null}
          {competitorSeedsQuery.isError ? (
            <p className="text-sm text-red-200">竞品样例加载失败：{competitorSeedsQuery.error.message}</p>
          ) : null}

          {!competitorSeedsQuery.isLoading && !competitorSeedsQuery.isError ? (
            <form className="space-y-5" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="user-query">
                  分析问题
                </label>
                <textarea
                  className="min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none ring-0 focus:border-primary"
                  id="user-query"
                  onChange={(event) => setUserQuery(event.target.value)}
                  value={userQuery}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="domain-hint">
                  领域提示（可选）
                </label>
                <textarea
                  className="min-h-20 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none ring-0 focus:border-primary"
                  id="domain-hint"
                  onChange={(event) => setDomainHint(event.target.value)}
                  placeholder="例如：协作知识库产品、B2B SaaS、面向企业采购决策"
                  value={domainHint}
                />
                <p className="text-xs text-muted-foreground">作为运行时 hint，帮助 Agent 更快选定信息源和维度。</p>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">竞品（自动补全 + 自由输入）</p>
                <div className="flex gap-2">
                  <input
                    className="h-9 flex-1 rounded-md border border-input bg-transparent px-3 text-sm outline-none ring-0 focus:border-primary"
                    onChange={(event) => setCompetitorInput(event.target.value)}
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
                  <Button onClick={() => addCompetitor(competitorInput)} type="button" variant="outline">
                    添加
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {competitorSuggestions.map((item) => (
                    <button
                      className="rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
                      key={item.id}
                      onClick={() => addCompetitor(item.display_name)}
                      type="button"
                    >
                      {item.display_name}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedCompetitors.map((item) => (
                    <button
                      className="rounded-md border border-primary/40 bg-primary/10 px-2 py-1 text-xs"
                      key={item}
                      onClick={() => removeCompetitor(item)}
                      type="button"
                    >
                      {item} ×
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">参考 URL（可选）</p>
                <div className="flex gap-2">
                  <input
                    className="h-9 flex-1 rounded-md border border-input bg-transparent px-3 text-sm outline-none ring-0 focus:border-primary"
                    onChange={(event) => setReferenceUrlInput(event.target.value)}
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
                  <Button onClick={() => addReferenceUrl(referenceUrlInput)} type="button" variant="outline">
                    添加
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {referenceUrls.map((item) => (
                    <button
                      className="rounded-md border border-border px-2 py-1 text-xs"
                      key={item}
                      onClick={() => removeReferenceUrl(item)}
                      type="button"
                    >
                      {item} ×
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">关注角色</p>
                <div className="flex flex-wrap gap-2">
                  {ROLE_OPTIONS.map((role) => (
                    <label
                      className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm"
                      key={role.id}
                    >
                      <input
                        checked={targetRoles.includes(role.id)}
                        onChange={() => toggleRole(role.id)}
                        type="checkbox"
                      />
                      <span>{role.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {createRunMutation.isError ? (
                <p className="text-sm text-red-200">创建失败：{createRunMutation.error.message}</p>
              ) : null}

              <div className="flex justify-end">
                <Button disabled={!canSubmit} type="submit">
                  {createRunMutation.isPending ? "启动中..." : "启动分析"}
                </Button>
              </div>
            </form>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
