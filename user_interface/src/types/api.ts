export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

export interface UserProfile {
  id: string;
  username: string;
  role: UserRole;
  court?: string;
  court_station?: string;
  full_name?: string;
  email?: string;
  staff_number?: string;
  status?: string;
  bio?: string;
  phone?: string;
  avatar_presigned_url?: string;
  created_at?: string;
  activated_at?: string;
}

export type UserRole = "judge" | "magistrate" | "registrar" | "clerk" | "admin";

export interface ChatRequest {
  message: string;
  session_id: string;
}

export interface StreamEvent {
  event: "status" | "answer" | "error" | "done";
  step?: PipelineStep;
  content?: string;
  session_id?: string;
  message_id?: string;
}

export type PipelineStep = "planner" | "retriever" | "responder";

export interface FeedbackRequest {
  message_id: number;
  session_id: string;
  score: number; // 1 = thumbs up, -1 = thumbs down
  comment?: string;
}

export interface UploadPresignRequest {
  filename: string;
  content_type: string;
}

export interface UploadPresignResponse {
  upload_url: string;
  file_id: string;
  s3_key: string;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: Record<string, ServiceHealth>;
  timestamp: string;
  version: string;
}

export interface ServiceHealth {
  status: "healthy" | "degraded" | "unhealthy";
  latency_ms?: number;
  message?: string;
}

export interface SessionSummary {
  session_id: string;
  started_at: string;
  last_activity: string;
  message_count: number;
  preview: string;
}

export interface MessageRecord {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export type DocumentType = "court_order" | "judgment" | "pleading" | "affidavit";

export interface VerificationCheck {
  check: string;
  passed: boolean;
  detail: string;
}

export interface VerificationReport {
  authentic: boolean;
  confidence: number;
  document_type: string;
  extracted_metadata: Record<string, string>;
  verification_checks: VerificationCheck[];
  risk_flags: string[];
  summary: string;
}

export interface VerificationActivity {
  id: number;
  filename: string;
  document_type: string;
  case_number: string;
  authentic: boolean;
  confidence: number;
  report: VerificationReport;
  created_at: string;
}

export type CaseComplexity = "low" | "medium" | "high" | "very_high";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface PredictionRequest {
  case_type: string;
  court: string;
  parties_count: number;
  complexity: CaseComplexity;
  description: string;
}

export interface PredictionReport {
  estimated_months_min: number;
  estimated_months_max: number;
  confidence: number;
  similar_cases_found: number;
  key_factors: string[];
  risk_level: RiskLevel;
  summary: string;
}

export interface PredictionActivity {
  id: number;
  case_type: string;
  court: string;
  complexity: CaseComplexity;
  parties_count: number;
  estimated_months_min: number | null;
  estimated_months_max: number | null;
  confidence: number | null;
  risk_level: RiskLevel | null;
  report: PredictionReport;
  created_at: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  full_name: string;
  court_station: string;
  role: UserRole;
  staff_number?: string;
}

export interface PendingUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  court_station: string;
  staff_number?: string;
  status: "pending" | "approved" | "active" | "suspended";
  created_at: string;
  bio?: string;
  phone?: string;
  avatar_url?: string;
}

/** A user returned by GET /api/v1/auth/users (active, suspended, or approved). */
export interface ActiveUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  court_station: string;
  staff_number?: string;
  status: "approved" | "active" | "suspended";
  created_at: string;
  activated_at?: string;
  last_login_at?: string;
  bio?: string;
  phone?: string;
  avatar_url?: string;
}
