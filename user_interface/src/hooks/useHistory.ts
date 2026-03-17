"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { SessionSummary, MessageRecord } from "@/types/api";

export function useHistory() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);

  useEffect(() => {
    apiFetch<SessionSummary[]>("/api/proxy/history/sessions")
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  const selectSession = useCallback((id: string) => {
    setSelectedId(id);
    setMessagesLoading(true);
    apiFetch<MessageRecord[]>(`/api/proxy/history/sessions/${id}`)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setMessagesLoading(false));
  }, []);

  return { sessions, loading, selectedId, messages, messagesLoading, selectSession };
}
