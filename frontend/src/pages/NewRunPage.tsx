import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateRun, useIndustryPacks } from "@/api/hooks";
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
  const packsQuery = useIndustryPacks();
  const createRunMutation = useCreateRun();

  const [userQuery, setUserQuery] = useState("AI Coding 工具竞争格局分析");
  const [industryPack, setIndustryPack] = useState("");
  const [selectedCompetitors, setSelectedCompetitors] = useState<string[]>([]);
  const [targetRoles, setTargetRoles] = useState<string[]>(["pm", "founder"]);

  const packs = packsQuery.data ?? [];
  const selectedPack = useMemo(
    () => packs.find((item) => item.id === industryPack) ?? null,
    [industryPack, packs],
  );

  useEffect(() => {
    if (packs.length === 0) {
      return;
    }
    if (industryPack && packs.some((pack) => pack.id === industryPack)) {
      return;
    }
    const firstPack = packs[0];
    setIndustryPack(firstPack.id);
    setSelectedCompetitors(firstPack.competitors.map((item) => item.id));
  }, [industryPack, packs]);

  const canSubmit =
    userQuery.trim().length > 0 &&
    industryPack.length > 0 &&
    selectedCompetitors.length > 0 &&
    !createRunMutation.isPending;

  function toggleCompetitor(competitorId: string): void {
    setSelectedCompetitors((prev) => {
      if (prev.includes(competitorId)) {
        return prev.filter((item) => item !== competitorId);
      }
      return [...prev, competitorId];
    });
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
      industry_pack: industryPack,
      target_roles: targetRoles,
    });
    navigate(`/runs/${created.run_id}`);
  }

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">新建分析任务</h1>
        <p className="text-sm text-muted-foreground">填写赛道问题、选择行业包和竞品后立即启动 run。</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">任务参数</CardTitle>
        </CardHeader>
        <CardContent>
          {packsQuery.isLoading ? <p className="text-sm text-muted-foreground">行业包加载中...</p> : null}
          {packsQuery.isError ? (
            <p className="text-sm text-red-200">行业包加载失败：{packsQuery.error.message}</p>
          ) : null}

          {!packsQuery.isLoading && !packsQuery.isError ? (
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
                <label className="text-sm font-medium" htmlFor="industry-pack">
                  行业包
                </label>
                <select
                  className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                  id="industry-pack"
                  onChange={(event) => {
                    const nextPackId = event.target.value;
                    const nextPack = packs.find((item) => item.id === nextPackId);
                    setIndustryPack(nextPackId);
                    setSelectedCompetitors(nextPack ? nextPack.competitors.map((item) => item.id) : []);
                  }}
                  value={industryPack}
                >
                  {packs.map((pack) => (
                    <option key={pack.id} value={pack.id}>
                      {pack.display_name}
                    </option>
                  ))}
                </select>
                {selectedPack ? (
                  <p className="text-xs text-muted-foreground">
                    默认维度：{selectedPack.research_dimensions.join(" / ")}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">竞品（多选）</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {selectedPack?.competitors.map((competitor) => (
                    <label
                      className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                      key={competitor.id}
                    >
                      <input
                        checked={selectedCompetitors.includes(competitor.id)}
                        onChange={() => toggleCompetitor(competitor.id)}
                        type="checkbox"
                      />
                      <span>{competitor.display_name}</span>
                    </label>
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
