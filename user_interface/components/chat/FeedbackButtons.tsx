"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useChatStore } from "@/store/chatStore";

interface FeedbackButtonsProps {
  messageId: string;
  sessionId: string;
  feedbackGiven?: "thumbs_up" | "thumbs_down";
}

export function FeedbackButtons({
  messageId,
  sessionId,
  feedbackGiven,
}: FeedbackButtonsProps) {
  const setMessageFeedback = useChatStore((s) => s.setMessageFeedback);
  const [toast, setToast] = useState(false);

  async function submit(rating: "thumbs_up" | "thumbs_down") {
    setMessageFeedback(sessionId, messageId, rating);
    try {
      await apiFetch("/api/v1/feedback/", {
        method: "POST",
        body: JSON.stringify({ message_id: messageId, session_id: sessionId, rating }),
      });
    } catch {
      // best-effort
    }
    setToast(true);
    setTimeout(() => setToast(false), 2000);
  }

  if (toast) {
    return <span className="text-xs text-green-600">Feedback recorded ✓</span>;
  }

  return (
    <div className="flex items-center gap-1 mt-1">
      <Button
        variant="ghost"
        size="sm"
        className={`h-6 px-2 text-xs ${feedbackGiven === "thumbs_up" ? "text-green-600" : "text-gray-400 hover:text-green-600"}`}
        onClick={() => submit("thumbs_up")}
        disabled={!!feedbackGiven}
      >
        👍
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className={`h-6 px-2 text-xs ${feedbackGiven === "thumbs_down" ? "text-red-500" : "text-gray-400 hover:text-red-500"}`}
        onClick={() => submit("thumbs_down")}
        disabled={!!feedbackGiven}
      >
        👎
      </Button>
    </div>
  );
}
