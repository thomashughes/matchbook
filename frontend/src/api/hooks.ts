/**
 * TanStack Query hooks for the Matchbook API.
 *
 * Why TanStack Query:
 *   Manual loading/error/cache state across 10+ pages would be a
 *   maintenance tax. Query handles caching, dedup, refetch-on-
 *   invalidate, and stale-while-revalidate out of the box.
 *
 * Key naming convention:
 *   ['entity', ...filters?] — so mutations can invalidate entity-wide
 *   with queryClient.invalidateQueries({ queryKey: ['jobs'] }).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './client';
import { uploadFile } from './upload';
import type {
  AIOutputKind,
  BillingStatus,
  CompanyResearch,
  CoverLetter,
  CvAnswer,
  CvQuestion,
  CvTone,
  CvVersion,
  FollowUpChannel,
  FollowUpStage,
  InterviewPrepRound,
  JobAIOutput,
  JobDetail,
  JobListItem,
  OutreachChannel,
  OutreachRecipientRole,
  Profile,
  Question,
} from '@/types/models';

// --- Profile --------------------------------------------------------------

export function useProfile() {
  return useQuery({
    queryKey: ['profile'],
    queryFn: () => api<Profile>('/profile'),
    // 404 means "no profile yet" — don't retry, just let the caller
    // render onboarding CTA.
    retry: false,
  });
}

export function useClarifyingQuestions(enabled: boolean) {
  return useQuery({
    queryKey: ['profile', 'questions'],
    queryFn: () => api<{ questions: Question[] }>('/profile/questions'),
    enabled,
    // Cache for the whole onboarding session — questions are expensive
    // to regenerate and shouldn't change mid-flow.
    staleTime: Infinity,
  });
}

export function useSubmitAnswers() {
  const qc = useQueryClient();
  // Backend schema (AnswerIn) keys questions by their text, not by id —
  // that's the audit record we want to store. `kind` lets the profile
  // generator weight typed answers (salary/remote/etc.) differently from
  // free-text. Defaults to 'free_text' to match the Pydantic default.
  return useMutation({
    mutationFn: (
      answers: { question: string; answer: string; kind?: string }[],
    ) => api<Profile>('/profile/answers', { method: 'POST', body: { answers } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile'] }),
  });
}

// --- Jobs -----------------------------------------------------------------

export function useJobs(q?: string) {
  return useQuery({
    queryKey: ['jobs', q ?? ''],
    queryFn: () =>
      api<JobListItem[]>(`/jobs${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  });
}

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: ['jobs', 'detail', id],
    queryFn: () => api<JobDetail>(`/jobs/${id}`),
    enabled: !!id,
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      source_type: 'paste' | 'url' | 'extension';
      description?: string;
      url?: string;
      title?: string;
      company?: string;
    }) => api<JobDetail>('/jobs', { method: 'POST', body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      // jobs_created is a per-user counter — refresh the dashboard pill
      // so the "X of Y jobs this month" reading updates after creation.
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

export function useCreateJobFromPdf() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadFile<JobDetail>('/jobs/from-pdf', file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

export function usePatchJob(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { status?: string; notes?: string }) =>
      api<JobDetail>(`/jobs/${id}`, { method: 'PATCH', body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['jobs', 'detail', id] });
    },
  });
}

export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/jobs/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
}

// --- Cover letters --------------------------------------------------------

export function useCoverLetters(jobId: string | undefined) {
  return useQuery({
    queryKey: ['jobs', 'detail', jobId, 'cover-letters'],
    queryFn: () => api<CoverLetter[]>(`/jobs/${jobId}/cover-letters`),
    enabled: !!jobId,
  });
}

export function useGenerateCoverLetter(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { tone: string; length: string }) =>
      api<CoverLetter>(`/jobs/${jobId}/cover-letters`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs', 'detail', jobId, 'cover-letters'] });
      // Per-job quota lives on JobDetail; refresh it so the button
      // caption ("2 cover letters left this month") re-renders.
      qc.invalidateQueries({ queryKey: ['jobs', 'detail', jobId] });
    },
  });
}

export function useDeleteCoverLetter(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (letterId: string) =>
      api<void>(`/jobs/${jobId}/cover-letters/${letterId}`, { method: 'DELETE' }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['jobs', 'detail', jobId, 'cover-letters'] }),
  });
}

// --- Generic AI outputs (outreach / form_response / follow_up / interview_prep) --

export function useAIOutputs(jobId: string | undefined, kind: AIOutputKind) {
  return useQuery({
    queryKey: ['jobs', 'detail', jobId, 'ai-outputs', kind],
    queryFn: () =>
      api<JobAIOutput[]>(`/jobs/${jobId}/ai-outputs?kind=${kind}`),
    enabled: !!jobId,
  });
}

export function useDeleteAIOutput(jobId: string, kind: AIOutputKind) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (outputId: string) =>
      api<void>(`/jobs/${jobId}/ai-outputs/${outputId}`, { method: 'DELETE' }),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: ['jobs', 'detail', jobId, 'ai-outputs', kind],
      }),
  });
}

// Shared helper: every per-job generation needs to refresh both the
// output-list query (the new draft appears) and the JobDetail query
// (its quota block reflects one-less credit). Factored out to avoid
// four identical 2-line onSuccess blocks below.
function invalidateAfterJobAI(qc: ReturnType<typeof useQueryClient>, jobId: string, kind: AIOutputKind) {
  qc.invalidateQueries({ queryKey: ['jobs', 'detail', jobId, 'ai-outputs', kind] });
  qc.invalidateQueries({ queryKey: ['jobs', 'detail', jobId] });
}

export function useGenerateOutreach(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      channel: OutreachChannel;
      recipient_role: OutreachRecipientRole;
      recipient_name?: string | null;
    }) =>
      api<JobAIOutput>(`/jobs/${jobId}/ai-outputs/outreach`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateAfterJobAI(qc, jobId, 'outreach'),
  });
}

export function useGenerateFormResponse(jobId: string) {
  const qc = useQueryClient();
  // form_response is the one AI action where the user's input (the
  // question) is itself the primary knob — hence a free-text body
  // rather than an enum pair. max_words is optional because Claude
  // can usually infer a sensible length from the question framing.
  return useMutation({
    mutationFn: (body: { question: string; max_words?: number | null }) =>
      api<JobAIOutput>(`/jobs/${jobId}/ai-outputs/form-response`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateAfterJobAI(qc, jobId, 'form_response'),
  });
}

export function useGenerateFollowUp(jobId: string) {
  const qc = useQueryClient();
  // stage is mandatory and drives the whole message shape; context is
  // optional free-text for a specific callback ("thanks for the book
  // recommendation"). Kept as a separate hook from outreach because
  // the endpoint + invalidation key differ.
  return useMutation({
    mutationFn: (body: {
      stage: FollowUpStage;
      channel: FollowUpChannel;
      context?: string | null;
    }) =>
      api<JobAIOutput>(`/jobs/${jobId}/ai-outputs/follow-up`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateAfterJobAI(qc, jobId, 'follow_up'),
  });
}

export function useGenerateInterviewPrep(jobId: string) {
  const qc = useQueryClient();
  // Round is the primary knob — it shifts the technical/behavioural
  // balance and the kind of "questions to ask" the sheet suggests.
  // focus is an optional topic bias ("system design", "React hooks").
  return useMutation({
    mutationFn: (body: {
      round: InterviewPrepRound;
      focus?: string | null;
    }) =>
      api<JobAIOutput>(`/jobs/${jobId}/ai-outputs/interview-prep`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => invalidateAfterJobAI(qc, jobId, 'interview_prep'),
  });
}

// --- Company research -----------------------------------------------------

export function useCompanyResearch(jobId: string | undefined) {
  return useQuery<CompanyResearch, ApiError>({
    queryKey: ['jobs', 'detail', jobId, 'company-research'],
    queryFn: () =>
      api<CompanyResearch>(`/jobs/${jobId}/company-research`),
    enabled: !!jobId,
    // Server's cached_at/expires_at is the source of staleness truth.
    // Avoid re-fetching on window focus / remount — that would duplicate
    // the same read during normal navigation.
    staleTime: Infinity,
    // 404 = "not researched yet", 400 = "job has no company name".
    // Neither is transient — don't retry, let the component branch on
    // the error status.
    retry: (count, err) => {
      if (err instanceof ApiError && (err.status === 404 || err.status === 400)) {
        return false;
      }
      return count < 2;
    },
  });
}

export function useGenerateCompanyResearch(jobId: string) {
  const qc = useQueryClient();
  // POST triggers a fresh Claude + web_search run and upserts the
  // shared cache. On success we write directly into the GET query's
  // cache so the UI flips to the loaded state without a second round-
  // trip to the server.
  return useMutation<CompanyResearch, ApiError, void>({
    mutationFn: () =>
      api<CompanyResearch>(`/jobs/${jobId}/company-research`, {
        method: 'POST',
      }),
    onSuccess: (data) => {
      qc.setQueryData(
        ['jobs', 'detail', jobId, 'company-research'],
        data,
      );
      // company_research is a per-user counter — refresh the pill.
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

// --- Billing --------------------------------------------------------------

/**
 * Plan + usage snapshot. Dashboard pill and /billing page both read
 * from here. Refetched automatically after generation mutations so
 * the "X of Y used" counter stays accurate without a page reload.
 *
 * staleTime is short (not zero) so navigating between pages within a
 * few seconds doesn't re-fire the query; long enough to feel snappy,
 * short enough that returning to /billing after upgrading shows the
 * flipped plan.
 */
export function useBillingStatus() {
  return useQuery({
    queryKey: ['billing', 'status'],
    queryFn: () => api<BillingStatus>('/billing/status'),
    staleTime: 15_000,
  });
}

/**
 * Start a Stripe Checkout session and redirect the browser to it.
 * The hook returns the mutation so callers can show a loading state
 * on the upgrade button; the actual redirect happens inside onSuccess
 * to keep the logic colocated with the only code path that uses it.
 */
export function useCreateCheckout() {
  return useMutation({
    mutationFn: () =>
      api<{ url: string }>('/billing/checkout', { method: 'POST' }),
    onSuccess: (data) => {
      window.location.href = data.url;
    },
  });
}

/**
 * Open the Stripe Customer Portal for the current user. Same redirect
 * pattern as checkout.
 */
export function useOpenBillingPortal() {
  return useMutation({
    mutationFn: () =>
      api<{ url: string }>('/billing/portal', { method: 'POST' }),
    onSuccess: (data) => {
      window.location.href = data.url;
    },
  });
}

export function useRescoreJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<JobDetail>(`/jobs/${id}/score`, { method: 'POST' }),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['jobs', 'detail', id] });
    },
  });
}

// --- Profile rebuild ------------------------------------------------------

/**
 * Wipe the user's profile + bump users.profile_version. After this,
 * existing jobs / cover letters / CVs are marked as "generated against
 * a previous profile" via their stored profile_version field.
 *
 * On success we invalidate EVERY relevant query — the user's next
 * navigation shouldn't see stale score rings or letter panels rendered
 * with pre-rebuild data.
 */
export function useRebuildProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>('/profile/rebuild', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profile'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['cv'] });
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

// --- CV generator ---------------------------------------------------------

/**
 * Remaining CV-generation credits for the current billing window.
 * Separate from /billing/status so the CV page can read just this
 * single number without pulling the full usage block.
 */
export function useCvQuota() {
  return useQuery({
    queryKey: ['cv', 'quota'],
    queryFn: () => api<{ remaining: number | null }>('/cv/status/quota'),
    // Short stale so the count refreshes after generating without a
    // full page reload. Not zero — two consecutive page mounts within
    // a few seconds shouldn't hammer the endpoint.
    staleTime: 10_000,
  });
}

/**
 * List every CV version the user has generated, newest first. Mirrors
 * how cover letters are listed — auto-open the latest in the UI.
 */
export function useCvVersions() {
  return useQuery({
    queryKey: ['cv', 'versions'],
    queryFn: () => api<CvVersion[]>('/cv'),
  });
}

/**
 * Generate Phase-1 questions. Doesn't cost a credit; the route is
 * Claude-backed so we bounce through a mutation (to match the
 * request/response lifecycle) rather than a query.
 */
export function useCvPhaseOne() {
  return useMutation<{ questions: CvQuestion[] }, Error, void>({
    mutationFn: () =>
      api<{ questions: CvQuestion[] }>('/cv/phase-one', { method: 'POST' }),
  });
}

/**
 * Generate Phase-2 CV rewrite. Costs one cv_generation credit.
 * On success we invalidate the version list + quota + billing status.
 */
export function useCvPhaseTwo() {
  const qc = useQueryClient();
  return useMutation<
    CvVersion,
    Error,
    {
      answers: CvAnswer[];
      tone: CvTone;
      extra_notes: string;
      regenerate_reason: string | null;
    }
  >({
    mutationFn: (body) =>
      api<CvVersion>('/cv', { method: 'POST', body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cv', 'versions'] });
      qc.invalidateQueries({ queryKey: ['cv', 'quota'] });
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

/**
 * Save the user's inline edits to an existing CV version in place. No
 * new version created — edits track against the existing row so the
 * version list stays clean.
 */
export function useUpdateCvVersion() {
  const qc = useQueryClient();
  return useMutation<
    CvVersion,
    Error,
    { id: string; content_markdown: string }
  >({
    mutationFn: ({ id, content_markdown }) =>
      api<CvVersion>(`/cv/${id}`, {
        method: 'PUT',
        body: { content_markdown },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cv', 'versions'] });
    },
  });
}

export function useDeleteCvVersion() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => api<void>(`/cv/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cv', 'versions'] });
    },
  });
}

/**
 * Regenerate a CV using a source version's stored answers plus a new
 * "what I want different" reason. No Phase-1 questionnaire — the
 * prior Phase-1 answers are loaded server-side from the source
 * version's questions_payload.
 */
export function useRegenerateCv() {
  const qc = useQueryClient();
  return useMutation<
    CvVersion,
    Error,
    { cvId: string; reason: string; tone?: CvTone }
  >({
    mutationFn: ({ cvId, reason, tone }) =>
      api<CvVersion>(`/cv/${cvId}/regenerate`, {
        method: 'POST',
        body: { reason, tone },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cv', 'versions'] });
      qc.invalidateQueries({ queryKey: ['cv', 'quota'] });
      qc.invalidateQueries({ queryKey: ['billing', 'status'] });
    },
  });
}

/**
 * Re-parse a chosen CV version and refresh the user's profile typed
 * fields (seniority, skills, salary, …) using the existing onboarding
 * answers. Bumps users.profile_version so jobs + cover letters show
 * stale banners until re-scored / regenerated.
 */
export function useRebuildProfileFromCv() {
  const qc = useQueryClient();
  return useMutation<Profile, Error, string>({
    mutationFn: (cvId) =>
      api<Profile>(`/cv/${cvId}/rebuild-profile`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profile'] });
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['cv'] });
    },
  });
}
