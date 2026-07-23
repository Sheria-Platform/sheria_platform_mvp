"use client";

import { useState } from "react";
import { useAllJobs } from "@/hooks/useIngestionJobs";
import { JobRow } from "@/components/jobs/JobRow";
import { cn } from "@/lib/utils";
import { Loader2, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

type Tab = "all" | "running" | "done" | "failed";

const TAB_LABELS: Record<Tab, string> = {
  all: "All",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

export default function JobsPage() {
  const { jobs, loading, refresh } = useAllJobs();
  const [tab, setTab] = useState<Tab>("all");

  const counts: Record<Tab, number> = {
    all: jobs.length,
    running: jobs.filter((j) => j.status === "pending" || j.status === "running").length,
    done: jobs.filter((j) => j.status === "done").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };

  const filtered =
    tab === "all"
      ? jobs
      : tab === "running"
      ? jobs.filter((j) => j.status === "pending" || j.status === "running")
      : jobs.filter((j) => j.status === tab);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ingestion Jobs</h1>
          <p className="text-sm text-gray-500 mt-1">
            Track document indexing runs — live and historical.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={refresh}
          className="gap-2 text-gray-500 hover:text-gray-700"
        >
          <RefreshCw size={14} />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {(["all", "running", "done", "failed"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "rounded-xl border px-4 py-3 text-left transition-all",
              tab === t
                ? "border-gray-900 bg-gray-900 text-white"
                : "border-gray-200 bg-white hover:border-gray-300"
            )}
          >
            <p className={cn("text-2xl font-bold", tab !== t && "text-gray-800")}>
              {counts[t]}
            </p>
            <p className={cn("text-xs mt-0.5", tab === t ? "text-gray-300" : "text-gray-400")}>
              {TAB_LABELS[t]}
            </p>
          </button>
        ))}
      </div>

      {/* Job list */}
      <div className="bg-white border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading jobs…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <FileText size={32} className="mb-3 opacity-30" />
            <p className="text-sm">
              {tab === "all"
                ? "No ingestion jobs yet. Upload a document to get started."
                : `No ${TAB_LABELS[tab].toLowerCase()} jobs.`}
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
