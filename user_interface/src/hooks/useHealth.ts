"use client";

import { useState, useEffect } from "react";
import { HealthResponse, ServiceHealth } from "@/types/api";

// NOTE: This hook calls FastAPI directly (bypassing the Next.js BFF proxy)
// because /health/readiness is a public endpoint that requires no authentication.
// In production, ensure CORS is configured on FastAPI to allow requests from the
// UI origin for this endpoint. If CORS restrictions become a problem, create
// app/api/proxy/health/route.ts and update the fetch URL below to "/api/proxy/health/readiness".
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ReadinessRaw = Record<string, "up" | "down">;

function toHealthResponse(raw: ReadinessRaw): HealthResponse {
  const services: Record<string, ServiceHealth> = {};
  for (const [name, state] of Object.entries(raw)) {
    services[name] = { status: state === "up" ? "healthy" : "unhealthy" };
  }
  const statuses = Object.values(services).map((s) => s.status);
  const allHealthy = statuses.every((s) => s === "healthy");
  const allUnhealthy = statuses.length > 0 && statuses.every((s) => s === "unhealthy");
  return {
    status: allHealthy ? "healthy" : allUnhealthy ? "unhealthy" : "degraded",
    services,
    timestamp: new Date().toISOString(),
    version: "",
  };
}

export function useHealth(pollInterval = 30_000) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/health/readiness`, {
          headers: { Accept: "application/json" },
        });
        // Accept both 200 (all up) and 503 (some down) — both carry the status dict.
        if (!res.ok && res.status !== 503) {
          throw new Error(`HTTP ${res.status}`);
        }
        const raw: ReadinessRaw = await res.json();
        if (!cancelled) {
          setHealth(toHealthResponse(raw));
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
