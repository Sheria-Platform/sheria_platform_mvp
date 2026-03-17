import { PipelineStep, UserRole } from "./api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  pipelineSteps?: PipelineStepStatus[];
  feedbackGiven?: "thumbs_up" | "thumbs_down";
}

export interface PipelineStepStatus {
  step: PipelineStep;
  status: "pending" | "active" | "complete";
  startedAt?: number;
  completedAt?: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

export interface AuthUser {
  id: string;
  username: string;
  role: UserRole;
  court?: string;
  full_name?: string;
  avatar_url?: string;
}
