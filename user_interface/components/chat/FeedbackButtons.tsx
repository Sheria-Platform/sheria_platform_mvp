"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore } from "@/store/chatStore";

type UiState =
  | "idle"
  | "awaiting_comment"
  | "submitting"
  | "done_positive"
  | "done_rerun"
  | "done_skip";

interface FeedbackButtonsProps {
  messageId: string;
  sessionId: string;
  feedbackGiven?: "thumbs_up" | "thumbs_down";
  onRerun?: (comment: string) => void;
}

export function FeedbackButtons({
  messageId,
  sessionId,
  feedbackGiven,
  onRerun,
}: FeedbackButtonsProps) {
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);

  const initialState: UiState =
    feedbackGiven === "thumbs_up"
      ? "done_positive"
      : feedbackGiven === "thumbs_down"
        ? "done_skip"
        : "idle";

  const [uiState, setUiState] = useState<UiState>(initialState);
  const [comment, setComment] = useState("");

  async function postFeedback(score: 1 | -1, feedbackComment: string | null) {
    try {
      await fetch("/api/proxy/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message_id: messageId,
          score,
          comment: feedbackComment,
        }),
      });
    } catch {
      // best-effort
    }
  }

  async function handleThumbsUp() {
    setUiState("submitting");
    setMessageFeedback(sessionId, messageId, "thumbs_up");
    await postFeedback(1, null);
    setUiState("done_positive");
  }

  function handleThumbsDown() {
    setUiState("awaiting_comment");
  }

  async function handleSubmitComment() {
    if (!comment.trim()) return;
    setUiState("submitting");
    setMessageFeedback(sessionId, messageId, "thumbs_down");
    await postFeedback(-1, comment.trim());
    setUiState("done_rerun");
    onRerun?.(comment.trim());
  }

  async function handleSkip() {
    setUiState("submitting");
    setMessageFeedback(sessionId, messageId, "thumbs_down");
    await postFeedback(-1, null);
    setUiState("done_skip");
  }

  if (uiState === "done_positive" || uiState === "done_skip") {
    return <span className="text-xs text-green-600">Feedback recorded ✓</span>;
  }

  if (uiState === "done_rerun") {
    return (
      <span className="text-xs text-amber-600">
        Rerunning for a better answer...
      </span>
    );
  }

  if (uiState === "awaiting_comment") {
    return (
      <div className="flex flex-col gap-1 mt-1">
        <Textarea
          autoFocus
          className="text-xs min-h-[60px] resize-none"
          placeholder="What was wrong with this response?"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              handleSubmitComment();
            }
          }}
        />
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            className="h-6 px-3 text-xs"
            onClick={handleSubmitComment}
            disabled={!comment.trim()}
          >
            Submit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-gray-400"
            onClick={handleSkip}
          >
            Skip
          </Button>
        </div>
      </div>
    );
  }

  // idle or submitting
  return (
    <div className="flex items-center gap-1 mt-1">
      <Button
        variant="ghost"
        size="sm"
        className={`h-6 px-2 text-xs ${feedbackGiven === "thumbs_up" ? "text-green-600" : "text-gray-400 hover:text-green-600"}`}
        onClick={handleThumbsUp}
        disabled={uiState === "submitting" || !!feedbackGiven}
      >
        👍
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className={`h-6 px-2 text-xs ${feedbackGiven === "thumbs_down" ? "text-red-500" : "text-gray-400 hover:text-red-500"}`}
        onClick={handleThumbsDown}
        disabled={uiState === "submitting" || !!feedbackGiven}
      >
        👎
      </Button>
    </div>
  );
}
