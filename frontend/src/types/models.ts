/**
 * Shared TypeScript types mirroring the backend's Pydantic schemas.
 *
 * Hand-maintained (not generated) for now — we can wire up openapi-
 * typescript in Phase 5 if drift becomes painful. Keeping them terse:
 * backend is the source of truth, the UI just needs enough shape.
 */

export interface User {
  id: string;
  email: string;
  is_verified: boolean;
}

export interface Profile {
  id: string;
  seniority_level: string | null;
  hard_skills: string[] | null;
  soft_skills: string[] | null;
  salary_min: number | null;
  salary_ideal: number | null;
  remote_preference: string | null;
  notice_period: string | null;
  career_goals: string | null;
  structured_data: Record<string, unknown> | null;
  // True once structured_data.generated exists (i.e. the user has
  // completed onboarding's CV-upload + answer-submit steps). Drives
  // the top-bar "Continue onboarding" banner: shown when False.
  onboarding_complete: boolean;
  // Current profile version. Bumped on POST /profile/rebuild. Compared
  // against per-artefact `profile_version` fields (jobs / cover letters
  // / cv versions) to show "based on a previous profile" banners.
  profile_version: number;
}

export interface Question {
  id: string;
  text: string;
  kind: 'work_location' | 'salary' | 'remote' | 'notice' | 'free_text';
}

export interface JobScore {
  total_score: number;
  skills_score: number;
  experience_score: number;
  salary_score: number;
  location_score: number;
  culture_score: number;
  trajectory_score: number;
  strengths: string[] | null;
  weaknesses: string[] | null;
  red_flags: string[] | null;
  summary: string | null;
  scored_at: string;
}

export type JobStatus = 'saved' | 'applied' | 'interviewing' | 'offer' | 'rejected';

export interface JobListItem {
  id: string;
  title: string;
  company: string;
  location: string | null;
  status: JobStatus;
  source_type: string;
  created_at: string;
  total_score: number | null;
  salary_raw: string | null;
}

export type AIOutputKind =
  | 'outreach'
  | 'form_response'
  | 'follow_up'
  | 'interview_prep';

export interface JobAIOutput {
  id: string;
  job_id: string;
  kind: AIOutputKind;
  content: string;
  params: Record<string, unknown>;
  version: number;
  created_at: string;
}

export type OutreachChannel = 'linkedin_connection' | 'linkedin_inmail' | 'email';
export type OutreachRecipientRole =
  | 'hiring_manager'
  | 'recruiter'
  | 'team_member'
  | 'referral';

export type FollowUpStage =
  | 'post_application'
  | 'post_interview'
  | 'post_recruiter_call'
  | 'no_response';
export type FollowUpChannel = 'email' | 'linkedin';

export type InterviewPrepRound =
  | 'phone_screen'
  | 'technical'
  | 'behavioural'
  | 'final'
  | 'general';

export interface CompanyResearch {
  company_name: string;
  briefing: string;
  sources: string[];
  cached_at: string;
  expires_at: string;
  // True when the server just (re)generated this payload, false when
  // served from the shared cache. Drives the "freshly researched" vs
  // "cached" indicator in the panel header.
  fresh: boolean;
}

export interface CoverLetter {
  id: string;
  job_id: string;
  content: string;
  tone: 'formal' | 'conversational';
  length: 'short' | 'standard' | 'detailed';
  version: number;
  // Snapshot of user.profile_version at generation time. When it
  // differs from the user's current profile_version the UI shows a
  // "generated against previous profile" pill.
  profile_version: number;
  created_at: string;
}

// --- CV generator --------------------------------------------------------

export type CvTone = 'professional' | 'bold';

export type CvQuestionType = 'text' | 'textarea' | 'radio';

export interface CvQuestion {
  id: string;
  text: string;
  type: CvQuestionType;
  hint: string;
  options: string[];
}

export interface CvAnswer {
  id: string;
  question: string;
  answer: string;
}

export interface CvVersion {
  id: string;
  version: number;
  content_markdown: string;
  tone: string;
  profile_version: number;
  regenerate_reason: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Every resource that the entitlement system tracks.
 *
 * Kept as a union literal (not string) so the UI can pattern-match
 * exhaustively and the compiler catches missed cases when new
 * resources are added. Must match the keys in backend
 * `app/core/entitlements.py: RESOURCES`.
 */
export type EntitlementResource =
  | 'jobs_created'
  | 'company_research'
  | 'draft_outreach'
  | 'draft_form_response'
  | 'draft_follow_up'
  | 'draft_interview_prep'
  | 'cover_letter'
  | 'ai_job_search'
  | 'cv_generation';

/**
 * One row of the per-job quota block on JobDetail and the per-user
 * usage array on BillingStatus. `limit` + `remaining` are null when
 * the plan grants unlimited use (grandfathered accounts).
 */
export interface QuotaItem {
  resource: EntitlementResource;
  limit: number | null;
  used: number;
  remaining: number | null;
  resets_at: string;
}

export interface JobDetail {
  id: string;
  title: string;
  company: string;
  location: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_raw: string | null;
  description_raw: string;
  source_url: string | null;
  source_type: string;
  status: JobStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
  score: JobScore | null;
  // Profile version this job was last scored against. NULL if never
  // scored. UI compares against profile.profile_version to decide
  // whether to render the stale-score banner.
  scored_against_profile_version: number | null;
  // Present on GET/PATCH responses. create_job returns [] to avoid a
  // second DB query — the next GET will fill it.
  quota: QuotaItem[];
}

// --- Billing --------------------------------------------------------------

export type Plan = 'free' | 'paid' | 'paid_grandfathered';

export interface BillingStatus {
  plan: Plan;
  subscription_status: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  usage: QuotaItem[];
}
