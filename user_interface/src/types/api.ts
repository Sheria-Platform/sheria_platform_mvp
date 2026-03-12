export interface LoginRequest {
  username: string;
  password: string;
  role: UserRole;
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
  full_name?: string;
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
  message_id: string;
  session_id: string;
  rating: "thumbs_up" | "thumbs_down";
  comment?: string;
}

export interface UploadPresignRequest {
  filename: string;
  content_type: string;
}

export interface UploadPresignResponse {
  upload_url: string;
  file_id: string;
  expires_in: number;
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
