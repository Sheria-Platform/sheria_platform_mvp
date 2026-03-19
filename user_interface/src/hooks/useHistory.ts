"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { SessionSummary, MessageRecord } from "@/types/api";

export function useHistory() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SessionSummary[]>("/api/proxy/history/sessions")
      .then((data) => { setSessions(data); setError(null); })
      .catch((err) => { setError((err as Error).message); setSessions([]); })
      .finally(() => setLoading(false));
  }, []);

  const selectSession = useCallback((id: string) => {
    setSelectedId(id);
    setMessagesLoading(true);
    setSessionError(null);
    apiFetch<MessageRecord[]>(`/api/proxy/history/sessions/${id}`)
      .then((data) => { setMessages(data); setSessionError(null); })
      .catch((err) => { setSessionError((err as Error).message); setMessages([]); })
      .finally(() => setMessagesLoading(false));
  }, []);

  return { sessions, loading, error, selectedId, messages, messagesLoading, sessionError, selectSession };
}
