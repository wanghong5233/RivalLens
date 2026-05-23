import { useState } from "react";
import { Link } from "react-router-dom";

import { useApproveCandidate, useRejectCandidate, useSkillCandidates } from "@/api/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";

export function SkillStagingPage(): JSX.Element {
  const [statusFilter, setStatusFilter] = useState("staging");
  const [industryPackFilter, setIndustryPackFilter] = useState("ai_coding_tools");
  const [reviewedBy, setReviewedBy] = useState("owner_wh");
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const candidatesQuery = useSkillCandidates({
    status: statusFilter === "all" ? undefined : statusFilter,
    industry_pack: industryPackFilter.trim() || undefined,
    limit: 50,
    offset: 0,
  });
  const approveMutation = useApproveCandidate();
  const rejectMutation = useRejectCandidate();

  async function reviewCandidate(
    candidateId: string,
    action: "approve" | "reject",
  ): Promise<void> {
    const reviewer = reviewedBy.trim();
    if (!reviewer) {
      setActionError("reviewed_by 不能为空。");
      return;
    }

    setPendingCandidateId(candidateId);
    try {
      if (action === "approve") {
        await approveMutation.mutateAsync({ candidateId, reviewedBy: reviewer });
      } else {
        await rejectMutation.mutateAsync({ candidateId, reviewedBy: reviewer });
      }
      setActionError(null);
      await candidatesQuery.refetch();
    } catch (error) {
      if (error instanceof Error) {
        setActionError(error.message);
      } else {
        setActionError("审核操作失败，请稍后重试。");
      }
    } finally {
      setPendingCandidateId(null);
    }
  }

  return (
    <section className="space-y-4">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Skill 审核台</h1>
        <p className="text-sm text-muted-foreground">
          查看 Curator 生成的候选项，进行通过/拒绝审核。
        </p>
      </header>

      <Card>
        <CardContent className="grid gap-3 pt-6 md:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">状态筛选</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              onChange={(event) => setStatusFilter(event.target.value)}
              value={statusFilter}
            >
              <option value="all">all</option>
              <option value="staging">staging</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">industry_pack</span>
            <Input
              onChange={(event) => setIndustryPackFilter(event.target.value)}
              placeholder="ai_coding_tools"
              value={industryPackFilter}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">reviewed_by</span>
            <Input
              onChange={(event) => setReviewedBy(event.target.value)}
              placeholder="owner_wh"
              value={reviewedBy}
            />
          </label>
        </CardContent>
      </Card>

      {actionError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">{actionError}</CardContent>
        </Card>
      ) : null}

      {candidatesQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : null}

      {candidatesQuery.isError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">
            {candidatesQuery.error.message}
          </CardContent>
        </Card>
      ) : null}

      {!candidatesQuery.isLoading && !candidatesQuery.isError && candidatesQuery.data?.items.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            当前筛选条件下没有候选项。
          </CardContent>
        </Card>
      ) : null}

      {!candidatesQuery.isLoading && !candidatesQuery.isError ? (
        <div className="space-y-3">
          {candidatesQuery.data?.items.map((candidate) => {
            const isPending = pendingCandidateId === candidate.id;
            return (
              <Card key={candidate.id}>
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <CardTitle className="font-mono text-sm">{candidate.id}</CardTitle>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{candidate.candidate_type}</Badge>
                      <Badge variant="secondary">{candidate.confidence}</Badge>
                      <Badge>{candidate.status}</Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-muted-foreground">{candidate.rationale}</p>
                  <p className="text-xs text-muted-foreground">
                    pack: {candidate.industry_pack} · created: {formatDateTime(candidate.created_at)}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {candidate.supporting_run_ids.map((runId) => (
                      <Link
                        className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:border-primary hover:text-foreground"
                        key={runId}
                        to={`/runs/${runId}`}
                      >
                        {runId}
                      </Link>
                    ))}
                  </div>
                  <pre className="overflow-x-auto rounded-md border border-border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
                    {JSON.stringify(candidate.payload, null, 2)}
                  </pre>
                  {candidate.error ? (
                    <p className="text-xs text-red-200">error: {candidate.error}</p>
                  ) : null}
                  {candidate.status === "staging" ? (
                    <div className="flex items-center gap-2">
                      <Button
                        disabled={isPending}
                        onClick={() => reviewCandidate(candidate.id, "approve")}
                        size="sm"
                      >
                        通过并生效
                      </Button>
                      <Button
                        disabled={isPending}
                        onClick={() => reviewCandidate(candidate.id, "reject")}
                        size="sm"
                        variant="outline"
                      >
                        拒绝
                      </Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
