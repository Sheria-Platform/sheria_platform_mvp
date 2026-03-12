"use client";

import { useState, useEffect, useRef } from "react";
import { apiFetch } from "@/lib/api";

export interface JobState {
  job_id: string;
  status: "pending" | "running" | "done" | "failed";
  stats: Record<string, number>;
  error: string;
}

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
            const data = await apiFetch<JobState>(`/api/v1/upload/jobs/${id}`);
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
