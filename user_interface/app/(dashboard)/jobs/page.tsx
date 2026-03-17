"use client";

import { useState } from "react";
import { useAllJobs, JobState } from "@/hooks/useIngestionJobs";
import { cn } from "@/lib/utils";
import {
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  RefreshCw,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";

type Tab = "all" | "running" | "done" | "failed";

const TAB_LABELS: Record<Tab, string> = {
  all: "All",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

function statusIcon(s: JobState["status"]) {
  if (s === "running") return <Loader2 size={14} className="text-blue-500 animate-spin shrink-0" />;
  if (s === "done") return <CheckCircle size={14} className="text-green-500 shrink-0" />;
  if (s === "failed") return <XCircle size={14} className="text-red-500 shrink-0" />;
  return <Clock size={14} className="text-gray-400 shrink-0" />;
}

function statusPill(s: JobState["status"]) {
  const base = "text-xs px-2 py-0.5 rounded-full font-medium";
  if (s === "running") return <span className={cn(base, "bg-blue-50 text-blue-700")}>Running</span>;
  if (s === "done") return <span className={cn(base, "bg-green-50 text-green-700")}>Completed</span>;
  if (s === "failed") return <span className={cn(base, "bg-red-50 text-red-600")}>Failed</span>;
  return <span className={cn(base, "bg-gray-100 text-gray-500")}>Queued</span>;
}

function formatTs(ts: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("en-KE", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(s: number | null) {
  if (s == null) return "—";
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function JobRow({ job }: { job: JobState }) {
  const [expanded, setExpanded] = useState(false);
  const hasStats = job.stats && Object.keys(job.stats).length > 0;

  return (
    <div
      className="border-b last:border-0 cursor-pointer hover:bg-gray-50 transition-colors"
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        {statusIcon(job.status)}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <FileText size={13} className="text-gray-400 shrink-0" />
            <span className="text-sm font-medium text-gray-800 truncate">
              {job.filename || job.s3_key}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{job.s3_key}</p>
        </div>

        <div className="hidden sm:flex items-center gap-6 text-xs text-gray-400 shrink-0">
          <span title="Started">{formatTs(job.started_at)}</span>
          <span title="Duration">{formatDuration(job.duration_s)}</span>
        </div>

        {statusPill(job.status)}
      </div>

      {expanded && (
        <div className="px-4 pb-3 pt-0 ml-5">
          {job.error && (
            <p className="text-xs text-red-600 mb-2 font-mono">{job.error}</p>
          )}
          {hasStats ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                ["Files processed", job.stats.files_processed],
                ["Chunks created", job.stats.chunks_created],
                ["Vectors indexed", job.stats.vectors_indexed],
                ["Failed", job.stats.files_failed],
              ].map(([label, val]) => (
                <div key={label as string} className="bg-gray-50 rounded-lg px-3 py-2">
                  <p className="text-xs text-gray-400">{label as string}</p>
                  <p className="text-sm font-semibold text-gray-700 mt-0.5">
                    {val ?? "—"}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400">No stats available yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

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
