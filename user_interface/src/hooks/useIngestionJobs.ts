"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { apiFetch } from "@/lib/api";

export interface JobState {
  job_id: string;
  status: "pending" | "running" | "done" | "failed";
  filename: string;
  s3_key: string;
  started_at: number | null;
  completed_at: number | null;
  duration_s: number | null;
  stats: Record<string, number>;
  error: string;
}

/** Poll a specific set of job IDs (used on the upload page). */
export function useIngestionJobs(jobIds: string[]) {
  const [jobs, setJobs] = useState<Record<string, JobState>>({});
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (jobIds.length === 0) return;

    const poll = async () => {
      const active = jobIds.filter((id) => {
        const j = jobs[id];
        return !j || j.status === "pending" || j.status === "running";
      });
      if (active.length === 0) return;

      await Promise.all(
        active.map(async (id) => {
          try {
            const data = await apiFetch<JobState>(`/api/proxy/upload/jobs/${id}`);
            setJobs((prev) => ({ ...prev, [id]: data }));
          } catch {
            // ignore transient errors
          }
        })
      );
    };

    poll();
    timerRef.current = setInterval(poll, 3000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobIds.join(",")]);

  return jobs;
}

/** Fetch and poll all jobs (used on the dedicated Jobs page). */
export function useAllJobs(pollInterval = 4000) {
  const [jobs, setJobs] = useState<JobState[]>([]);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const data = await apiFetch<JobState[]>("/api/proxy/upload/jobs");
      setJobs(data);
    } catch {
      // ignore transient errors
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(() => {
      // only keep polling if there are active jobs
      setJobs((prev) => {
        const hasActive = prev.some(
          (j) => j.status === "pending" || j.status === "running"
        );
        if (hasActive) fetchAll();
        return prev;
      });
    }, pollInterval);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll, pollInterval]);

  const refresh = fetchAll;
  return { jobs, loading, refresh };
}
