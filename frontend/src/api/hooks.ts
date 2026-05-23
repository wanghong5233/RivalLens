import {
  useMutation,
  type UseMutationResult,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type {
  EvidenceListItemResponse,
  IndustryPackListItemResponse,
  RunCreateRequest,
  RunCreateResponse,
  RunDetailResponse,
  RunListResponse,
  RunReportResponse,
  RunTraceResponse,
  SkillCandidateListResponse,
  SkillCandidateReviewRequest,
  SkillCandidateReviewResponse,
} from "@/api/types";

const RUNNING_POLL_INTERVAL_MS = 2_000;

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
  industry_pack?: string;
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

async function fetchRunEvidence(
  runId: string,
  query: RunEvidenceQuery,
): Promise<EvidenceListItemResponse[]> {
  const { data } = await apiClient.get<EvidenceListItemResponse[]>(`/api/runs/${runId}/evidence`, {
    params: query,
  });
  return data;
}

async function fetchIndustryPacks(): Promise<IndustryPackListItemResponse[]> {
  const { data } = await apiClient.get<IndustryPackListItemResponse[]>("/api/industry-packs");
  return data;
}

async function createRun(payload: RunCreateRequest): Promise<RunCreateResponse> {
  const { data } = await apiClient.post<RunCreateResponse>("/api/runs", payload);
  return data;
}

async function resumeRun(runId: string): Promise<RunCreateResponse> {
  const { data } = await apiClient.post<RunCreateResponse>(`/api/runs/${runId}/resume`);
  return data;
}

async function fetchSkillCandidates(
  query: SkillCandidatesQuery,
): Promise<SkillCandidateListResponse> {
  const { data } = await apiClient.get<SkillCandidateListResponse>("/api/skill-candidates", {
    params: {
      status: query.status,
      industry_pack: query.industry_pack,
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
  return useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => fetchRunDetail(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? RUNNING_POLL_INTERVAL_MS : false,
  });
}

export function useRunTrace(runId: string): UseQueryResult<RunTraceResponse, Error> {
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

export function useIndustryPacks(): UseQueryResult<IndustryPackListItemResponse[], Error> {
  return useQuery({
    queryKey: ["industry-packs"],
    queryFn: fetchIndustryPacks,
  });
}

export function useCreateRun(): UseMutationResult<RunCreateResponse, Error, RunCreateRequest> {
  return useMutation({
    mutationFn: createRun,
  });
}

export function useResumeRun(): UseMutationResult<RunCreateResponse, Error, string> {
  return useMutation({
    mutationFn: resumeRun,
  });
}

export function useSkillCandidates(
  query: SkillCandidatesQuery = {},
): UseQueryResult<SkillCandidateListResponse, Error> {
  return useQuery({
    queryKey: [
      "skill-candidates",
      query.status ?? "",
      query.industry_pack ?? "",
      query.limit ?? 20,
      query.offset ?? 0,
    ],
    queryFn: () => fetchSkillCandidates(query),
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
