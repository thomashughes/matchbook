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
  created_at: string;
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
}
