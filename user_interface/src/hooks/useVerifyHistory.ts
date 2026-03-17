"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { VerificationActivity } from "@/types/api";

export function useVerifyHistory() {
  const [activities, setActivities] = useState<VerificationActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    apiFetch<VerificationActivity[]>("/api/v1/verify/history")
      .then((data) => {
        setActivities(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load history"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { activities, loading, error, refresh };
}
