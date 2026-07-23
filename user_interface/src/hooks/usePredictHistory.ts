"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { PredictionActivity } from "@/types/api";

export function usePredictHistory() {
  const [activities, setActivities] = useState<PredictionActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    apiFetch<PredictionActivity[]>("/api/proxy/predict/history")
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
