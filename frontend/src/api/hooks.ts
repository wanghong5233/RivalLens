import {
  useMutation,
  type UseMutationResult,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { getRunFallbackPollMs, useRunEvents } from "@/api/sse";
import type {
  CompetitorSeedResponse,
  EvidenceListItemResponse,
  FollowUpAcceptedResponse,
  FollowUpRequest,
  IntakeCreateRequest,
  IntakeCreateResponse,
  IntakeUserReply,
  PlanConfirmRequest,
  RunAcceptedResponse,
  RunCreateRequest,
  RunCreateResponse,
  RunDetailResponse,
  RunListResponse,
  RunMetricsResponse,
  RunConclusionsResponse,
  RunResetRequest,
  RunReportResponse,
  RunTraceResponse,
  SkillCandidateListResponse,
  SkillCandidateReviewRequest,
  SkillCandidateReviewResponse,
  WatchlistCreateRequest,
  WatchlistItemResponse,
} from "@/api/types";

const RUNNING_POLL_INTERVAL_MS = getRunFallbackPollMs();

export interface RunsListQuery {
  status?: string;
  limit?: number;
  offset?: number;
}

export interface RunEvidenceQuery {
  competitor_id?: string;
  source_type?: string;
}

export interface QueryBehaviorOptions {
  enabled?: boolean;
  refetchInterval?: number | false;
}

export interface SkillCandidatesQuery {
  status?: string;
  applies_to?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}

export interface ReviewSkillCandidateMutationVariables {
  candidateId: string;
  reviewedBy: string;
}

async function fetchRunsList(query: RunsListQuery): Promise<RunListResponse> {
  const { data } = await apiClient.get<RunListResponse>("/api/runs", {
    params: {
      status: query.status,
      limit: query.limit ?? 20,
      offset: query.offset ?? 0,
    },
  });
  return data;
}

async function fetchRunDetail(runId: string): Promise<RunDetailResponse> {
  const { data } = await apiClient.get<RunDetailResponse>(`/api/runs/${runId}`);
  return data;
}

async function fetchRunTrace(runId: string): Promise<RunTraceResponse> {
  const { data } = await apiClient.get<RunTraceResponse>(`/api/runs/${runId}/trace`);
  return data;
}

async function fetchRunReport(runId: string): Promise<RunReportResponse> {
  const { data } = await apiClient.get<RunReportResponse>(`/api/runs/${runId}/report`);
  return data;
}

async function fetchRunMetrics(runId: string): Promise<RunMetricsResponse> {
  const { data } = await apiClient.get<RunMetricsResponse>(`/api/runs/${runId}/metrics`);
  return data;
}

async function fetchRunConclusions(runId: string): Promise<RunConclusionsResponse> {
  const { data } = await apiClient.get<RunConclusionsResponse>(`/api/runs/${runId}/conclusions`);
  return data;
}

async function fetchWatchlist(): Promise<WatchlistItemResponse[]> {
  const { data } = await apiClient.get<WatchlistItemResponse[]>("/api/watchlist");
  return data;
}

async function createWatchlistItem(payload: WatchlistCreateRequest): Promise<WatchlistItemResponse> {
  const { data } = await apiClient.post<WatchlistItemResponse>("/api/watchlist", payload);
  return data;
}

async function deleteWatchlistItem(watchId: string): Promise<WatchlistItemResponse> {
  const { data } = await apiClient.delete<WatchlistItemResponse>(`/api/watchlist/${watchId}`);
  return data;
}

async function deleteRun(runId: string): Promise<{ run_id: string; deleted: boolean }> {
  const { data } = await apiClient.delete<{ run_id: string; deleted: boolean }>(`/api/runs/${runId}`);
  return data;
}

async function patchRun(
  runId: string,
  payload: {
    user_query?: string;
    title?: string;
    status?: "cancelled";
    cancel_reason?: string;
  },
): Promise<RunDetailResponse> {
  const { data } = await apiClient.patch<RunDetailResponse>(`/api/runs/${runId}`, payload);
  return data;
}

async function batchDeleteRuns(
  runIds: string[],
): Promise<{ deleted_count: number; not_found: string[] }> {
  const { data } = await apiClient.post<{ deleted_count: number; not_found: string[] }>(
    "/api/runs/batch-delete",
    { run_ids: runIds },
  );
  return data;
}

interface ClearRunsRequest {
  status?: "all" | "running" | "completed" | "degraded" | "failed" | "cancelled";
  keyword?: string;
  include_running?: boolean;
}

interface ClearRunsResponse {
  deleted_count: number;
  deleted_run_ids: string[];
  skipped_running_count: number;
  pruned_skill_candidate_refs: number;
}

async function clearRuns(payload: ClearRunsRequest): Promise<ClearRunsResponse> {
  const { data } = await apiClient.post<ClearRunsResponse>("/api/runs/clear", payload);
  return data;
}

async function fetchRunEvidence(
  runId: string,
  query: RunEvidenceQuery,
): Promise<EvidenceListItemResponse[]> {
  const { data } = await apiClient.get<EvidenceListItemResponse[]>(`/api/runs/${runId}/evidence`, {
    params: query,
  });
  return data;
}

async function fetchCompetitorSeeds(): Promise<CompetitorSeedResponse[]> {
  const { data } = await apiClient.get<CompetitorSeedResponse[]>("/api/demo-fixtures/competitors");
  return data;
}

async function createRun(payload: RunCreateRequest): Promise<RunCreateResponse> {
  const { data } = await apiClient.post<RunCreateResponse>("/api/runs", payload);
  return data;
}

async function createRunIntake(payload: IntakeCreateRequest): Promise<IntakeCreateResponse> {
  const { data } = await apiClient.post<IntakeCreateResponse>("/api/runs/intake", payload);
  return data;
}

export interface ReplyRunIntakeVariables {
  runId: string;
  reply: IntakeUserReply;
}

async function replyRunIntake(
  runId: string,
  reply: IntakeUserReply,
): Promise<RunAcceptedResponse> {
  const { data } = await apiClient.post<RunAcceptedResponse>(
    `/api/runs/${runId}/intake/reply`,
    reply,
  );
  return data;
}

async function confirmRunPlan(
  runId: string,
  payload: PlanConfirmRequest,
): Promise<RunAcceptedResponse> {
  const { data } = await apiClient.post<RunAcceptedResponse>(
    `/api/runs/${runId}/plan/confirm`,
    payload,
  );
  return data;
}

async function submitRunFollowUp(
  runId: string,
  payload: FollowUpRequest,
): Promise<FollowUpAcceptedResponse> {
  const { data } = await apiClient.post<FollowUpAcceptedResponse>(
    `/api/runs/${runId}/follow-up`,
    payload,
  );
  return data;
}

async function resumeRun(runId: string): Promise<RunCreateResponse> {
  const { data } = await apiClient.post<RunCreateResponse>(`/api/runs/${runId}/resume`);
  return data;
}

async function resetRun(runId: string, payload: RunResetRequest): Promise<RunCreateResponse> {
  const { data } = await apiClient.post<RunCreateResponse>(`/api/runs/${runId}/reset`, payload);
  return data;
}

async function fetchSkillCandidates(
  query: SkillCandidatesQuery,
): Promise<SkillCandidateListResponse> {
  const { data } = await apiClient.get<SkillCandidateListResponse>("/api/skill-candidates", {
    params: {
      status: query.status,
      applies_to: query.applies_to,
      tag: query.tag,
      limit: query.limit ?? 20,
      offset: query.offset ?? 0,
    },
  });
  return data;
}

async function approveSkillCandidate(
  candidateId: string,
  payload: SkillCandidateReviewRequest,
): Promise<SkillCandidateReviewResponse> {
  const { data } = await apiClient.post<SkillCandidateReviewResponse>(
    `/api/skill-candidates/${candidateId}/approve`,
    payload,
  );
  return data;
}

async function rejectSkillCandidate(
  candidateId: string,
  payload: SkillCandidateReviewRequest,
): Promise<SkillCandidateReviewResponse> {
  const { data } = await apiClient.post<SkillCandidateReviewResponse>(
    `/api/skill-candidates/${candidateId}/reject`,
    payload,
  );
  return data;
}

export function useRunsList(query: RunsListQuery = {}): UseQueryResult<RunListResponse, Error> {
  return useQuery({
    queryKey: ["runs", query.status ?? "", query.limit ?? 20, query.offset ?? 0],
    queryFn: () => fetchRunsList(query),
  });
}

export function useRunDetail(runId: string): UseQueryResult<RunDetailResponse, Error> {
  useRunEvents(runId);
  return useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => fetchRunDetail(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? RUNNING_POLL_INTERVAL_MS : false,
  });
}

export function useRunTrace(runId: string): UseQueryResult<RunTraceResponse, Error> {
  useRunEvents(runId);
  return useQuery({
    queryKey: ["run-trace", runId],
    queryFn: () => fetchRunTrace(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data?.run.status === "running" ? RUNNING_POLL_INTERVAL_MS : false,
  });
}

export function useRunReport(
  runId: string,
  options: QueryBehaviorOptions = {},
): UseQueryResult<RunReportResponse, Error> {
  return useQuery({
    queryKey: ["run-report", runId],
    queryFn: () => fetchRunReport(runId),
    enabled: Boolean(runId) && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useRunMetrics(
  runId: string,
  options: QueryBehaviorOptions = {},
): UseQueryResult<RunMetricsResponse, Error> {
  return useQuery({
    queryKey: ["run-metrics", runId],
    queryFn: () => fetchRunMetrics(runId),
    enabled: Boolean(runId) && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useRunConclusions(
  runId: string,
  options: QueryBehaviorOptions = {},
): UseQueryResult<RunConclusionsResponse, Error> {
  return useQuery({
    queryKey: ["run-conclusions", runId],
    queryFn: () => fetchRunConclusions(runId),
    enabled: Boolean(runId) && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useWatchlist(): UseQueryResult<WatchlistItemResponse[], Error> {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
  });
}

export function useRunEvidence(
  runId: string,
  query: RunEvidenceQuery = {},
  options: QueryBehaviorOptions = {},
): UseQueryResult<EvidenceListItemResponse[], Error> {
  return useQuery({
    queryKey: ["run-evidence", runId, query.competitor_id ?? "", query.source_type ?? ""],
    queryFn: () => fetchRunEvidence(runId, query),
    enabled: Boolean(runId) && (options.enabled ?? true),
    refetchInterval: options.refetchInterval,
  });
}

export function useCompetitorSeeds(): UseQueryResult<CompetitorSeedResponse[], Error> {
  return useQuery({
    queryKey: ["competitor-seeds"],
    queryFn: fetchCompetitorSeeds,
  });
}

export function useCreateRun(): UseMutationResult<RunCreateResponse, Error, RunCreateRequest> {
  return useMutation({
    mutationFn: createRun,
  });
}

export function useCreateRunIntake(): UseMutationResult<
  IntakeCreateResponse,
  Error,
  IntakeCreateRequest
> {
  return useMutation({
    mutationFn: createRunIntake,
  });
}

export function useReplyRunIntake(): UseMutationResult<
  RunAcceptedResponse,
  Error,
  ReplyRunIntakeVariables
> {
  return useMutation({
    mutationFn: ({ runId, reply }) => replyRunIntake(runId, reply),
  });
}

export interface ConfirmRunPlanVariables {
  runId: string;
  payload: PlanConfirmRequest;
}

export function useConfirmRunPlan(): UseMutationResult<
  RunAcceptedResponse,
  Error,
  ConfirmRunPlanVariables
> {
  return useMutation({
    mutationFn: ({ runId, payload }) => confirmRunPlan(runId, payload),
  });
}

export interface SubmitRunFollowUpVariables {
  runId: string;
  payload: FollowUpRequest;
}

export function useSubmitRunFollowUp(): UseMutationResult<
  FollowUpAcceptedResponse,
  Error,
  SubmitRunFollowUpVariables
> {
  return useMutation({
    mutationFn: ({ runId, payload }) => submitRunFollowUp(runId, payload),
  });
}

export function useResumeRun(): UseMutationResult<RunCreateResponse, Error, string> {
  return useMutation({
    mutationFn: resumeRun,
  });
}

export interface ResetRunMutationVariables {
  runId: string;
  resetTo: RunResetRequest["reset_to"];
}

export function useResetRun(): UseMutationResult<RunCreateResponse, Error, ResetRunMutationVariables> {
  return useMutation({
    mutationFn: ({ runId, resetTo }) => resetRun(runId, { reset_to: resetTo }),
  });
}

export function useCreateWatchlistItem(): UseMutationResult<
  WatchlistItemResponse,
  Error,
  WatchlistCreateRequest
> {
  return useMutation({
    mutationFn: createWatchlistItem,
  });
}

export function useDeleteWatchlistItem(): UseMutationResult<WatchlistItemResponse, Error, string> {
  return useMutation({
    mutationFn: deleteWatchlistItem,
  });
}

export function useSkillCandidates(
  query: SkillCandidatesQuery = {},
  options?: { errorToast?: boolean },
): UseQueryResult<SkillCandidateListResponse, Error> {
  return useQuery({
    queryKey: [
      "skill-candidates",
      query.status ?? "",
      query.applies_to ?? "",
      query.tag ?? "",
      query.limit ?? 20,
      query.offset ?? 0,
    ],
    queryFn: () => fetchSkillCandidates(query),
    meta: { errorToast: options?.errorToast ?? true },
  });
}

export function useApproveCandidate(): UseMutationResult<
  SkillCandidateReviewResponse,
  Error,
  ReviewSkillCandidateMutationVariables
> {
  return useMutation({
    mutationFn: ({ candidateId, reviewedBy }) =>
      approveSkillCandidate(candidateId, { reviewed_by: reviewedBy }),
  });
}

export function useRejectCandidate(): UseMutationResult<
  SkillCandidateReviewResponse,
  Error,
  ReviewSkillCandidateMutationVariables
> {
  return useMutation({
    mutationFn: ({ candidateId, reviewedBy }) =>
      rejectSkillCandidate(candidateId, { reviewed_by: reviewedBy }),
  });
}

export interface PatchRunVariables {
  runId: string;
  payload: {
    user_query?: string;
    title?: string;
    status?: "cancelled";
    cancel_reason?: string;
  };
}

export function useDeleteRun(): UseMutationResult<
  { run_id: string; deleted: boolean },
  Error,
  string
> {
  return useMutation({
    mutationFn: deleteRun,
  });
}

export function usePatchRun(): UseMutationResult<RunDetailResponse, Error, PatchRunVariables> {
  return useMutation({
    mutationFn: ({ runId, payload }) => patchRun(runId, payload),
  });
}

export function useBatchDeleteRuns(): UseMutationResult<
  { deleted_count: number; not_found: string[] },
  Error,
  string[]
> {
  return useMutation({
    mutationFn: batchDeleteRuns,
  });
}

export function useClearRuns(): UseMutationResult<
  ClearRunsResponse,
  Error,
  ClearRunsRequest
> {
  return useMutation({
    mutationFn: clearRuns,
  });
}
