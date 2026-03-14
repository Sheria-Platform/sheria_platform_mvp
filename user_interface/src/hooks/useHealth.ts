"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { HealthResponse } from "@/types/api";

export function useHealth(pollInterval = 30_000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const data = await apiFetch<HealthResponse>("/api/v1/health", {
          skipAuth: true,
          headers: { Accept: "application/json" },
        });
        if (!cancelled) {
          setHealth(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
          setLoading(false);
        }
      }
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollInterval]);

  return { health, loading, error };
}
