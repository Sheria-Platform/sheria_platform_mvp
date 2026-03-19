"use client";

import { useState } from "react";
import { useAllJobs } from "@/hooks/useIngestionJobs";
import { JobRow } from "@/components/jobs/JobRow";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Loader2, Layers, RefreshCw } from "lucide-react";

type JobStatusFilter = "all" | "running" | "done" | "failed";

const JOB_TAB_LABELS: Record<JobStatusFilter, string> = {
  all: "All",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

export function IngestionTab() {
  const { jobs, loading, refresh } = useAllJobs();
  const [filter, setFilter] = useState<JobStatusFilter>("all");

  const counts: Record<JobStatusFilter, number> = {
    all: jobs.length,
    running: jobs.filter((j) => j.status === "pending" || j.status === "running").length,
    done: jobs.filter((j) => j.status === "done").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };

  const filtered =
    filter === "all"
      ? jobs
      : filter === "running"
      ? jobs.filter((j) => j.status === "pending" || j.status === "running")
      : jobs.filter((j) => j.status === filter);

  return (
    <div className="flex-1 overflow-auto px-4 py-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-gray-500">Track document indexing runs — live and historical.</p>
        <Button variant="ghost" size="sm" onClick={refresh} className="gap-2 text-gray-500 hover:text-gray-700">
          <RefreshCw size={14} />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {(["all", "running", "done", "failed"] as JobStatusFilter[]).map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={cn(
              "rounded-xl border px-4 py-3 text-left transition-all",
              filter === t ? "border-gray-900 bg-gray-900 text-white" : "border-gray-200 bg-white hover:border-gray-300"
            )}
          >
            <p className={cn("text-2xl font-bold", filter !== t && "text-gray-800")}>{counts[t]}</p>
            <p className={cn("text-xs mt-0.5", filter === t ? "text-gray-300" : "text-gray-400")}>{JOB_TAB_LABELS[t]}</p>
          </button>
        ))}
      </div>

      <div className="bg-white border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading jobs…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Layers size={32} className="mb-3 opacity-30" />
            <p className="text-sm">
              {filter === "all" ? "No ingestion jobs yet. Upload a document to get started." : `No ${JOB_TAB_LABELS[filter].toLowerCase()} jobs.`}
            </p>
          </div>
        ) : (
          filtered.map((job) => <JobRow key={job.job_id} job={job} />)
        )}
      </div>

      {filtered.length > 0 && (
        <p className="text-xs text-gray-400 text-center mt-3">
          Click any row to expand stats · Auto-refreshes every 4 s while jobs are active
        </p>
      )}
    </div>
  );
}
