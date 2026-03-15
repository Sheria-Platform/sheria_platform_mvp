"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { useHistory } from "@/hooks/useHistory";
import { useAllJobs, JobState } from "@/hooks/useIngestionJobs";
import { useVerifyHistory } from "@/hooks/useVerifyHistory";
import { SessionSummary, MessageRecord, VerificationActivity } from "@/types/api";
import { VerificationReportCard } from "@/components/verify/VerificationReportCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  History,
  MessageSquare,
  ArrowRight,
  FileText,
  ShieldCheck,
  Layers,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ShieldX,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

// ── Shared helpers ─────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-KE", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type Tab = "chat" | "ingestion" | "verify";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "chat", label: "Chat History", icon: MessageSquare },
  { id: "ingestion", label: "Ingestion Jobs", icon: Layers },
  { id: "verify", label: "Verifications", icon: ShieldCheck },
];

// ── Chat tab ───────────────────────────────────────────────────────────────────

function SessionItem({
  session,
  active,
  onClick,
}: {
  session: SessionSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-3 py-3 rounded-lg transition-colors border",
        active
          ? "bg-gray-900 border-gray-900 text-white"
          : "bg-white border-gray-200 hover:border-gray-300 hover:bg-gray-50"
      )}
    >
      <p className={cn("text-sm font-medium leading-snug line-clamp-2", active ? "text-white" : "text-gray-800")}>
        {session.preview || "Empty session"}
      </p>
      <div className={cn("flex items-center justify-between mt-1.5", active ? "text-gray-300" : "text-gray-400")}>
        <span className="text-xs">{formatDate(session.last_activity)}</span>
        <span className={cn("text-xs px-1.5 py-0.5 rounded-full", active ? "bg-white/20" : "bg-gray-100")}>
          {session.message_count} msg
        </span>
      </div>
    </button>
  );
}

function MessageBubble({ message }: { message: MessageRecord }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex py-1", isUser ? "justify-end px-4" : "px-4")}>
      {isUser ? (
        <div className="max-w-[75%]">
          <div
            className="text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
            style={{ backgroundColor: "#1a3a6b" }}
          >
            {message.content}
          </div>
          <p className="text-xs text-gray-400 text-right mt-1">{formatDate(message.created_at)}</p>
        </div>
      ) : (
        <div className="max-w-[85%]">
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
            <div className="prose prose-sm prose-slate max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
                {message.content}
              </ReactMarkdown>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-1">{formatDate(message.created_at)}</p>
        </div>
      )}
    </div>
  );
}

function ChatTab() {
  const router = useRouter();
  const { setActiveSession } = useChatStore();
  const { sessions, loading, selectedId, messages, messagesLoading, selectSession } = useHistory();

  function handleLoadInChat() {
    if (!selectedId) return;
    setActiveSession(selectedId);
    router.push("/chat");
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Session list */}
      <div className="w-72 shrink-0 border-r bg-gray-50 flex flex-col">
        <ScrollArea className="flex-1 px-3 py-3">
          {loading ? (
            <div className="space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="space-y-1.5 rounded-lg border border-gray-200 p-3">
                  <Skeleton className="h-3.5 w-4/5" />
                  <Skeleton className="h-3 w-3/5" />
                  <Skeleton className="h-3 w-2/5" />
                </div>
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <MessageSquare size={28} className="mb-2 opacity-30" />
              <p className="text-xs text-center">No past sessions found.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {sessions.map((s) => (
                <SessionItem
                  key={s.session_id}
                  session={s}
                  active={s.session_id === selectedId}
                  onClick={() => selectSession(s.session_id)}
                />
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Message thread */}
      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        {selectedId ? (
          <>
            <div className="px-6 py-3 border-b bg-white shrink-0 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-800 truncate max-w-md">
                  {sessions.find((s) => s.session_id === selectedId)?.preview || "Session"}
                </p>
                <p className="text-xs text-gray-400">
                  {sessions.find((s) => s.session_id === selectedId)?.message_count ?? 0} messages · read-only
                </p>
              </div>
              <Button size="sm" onClick={handleLoadInChat} className="gap-1.5 text-xs h-8">
                Continue in Chat
                <ArrowRight size={13} />
              </Button>
            </div>
            <ScrollArea className="flex-1 py-4">
              {messagesLoading ? (
                <div className="space-y-4 px-4">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className={cn("flex", i % 2 === 0 ? "justify-end" : "justify-start")}>
                      <Skeleton className="h-12 w-2/3 rounded-2xl" />
                    </div>
                  ))}
                </div>
              ) : (
                messages.map((m) => <MessageBubble key={m.id} message={m} />)
              )}
            </ScrollArea>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 text-gray-400">
            <History size={40} className="mb-3 opacity-20" />
            <p className="text-sm">Select a session to view</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Ingestion tab ──────────────────────────────────────────────────────────────

type JobStatusFilter = "all" | "running" | "done" | "failed";

const JOB_TAB_LABELS: Record<JobStatusFilter, string> = {
  all: "All",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

function jobStatusIcon(s: JobState["status"]) {
  if (s === "running") return <Loader2 size={14} className="text-blue-500 animate-spin shrink-0" />;
  if (s === "done") return <CheckCircle size={14} className="text-green-500 shrink-0" />;
  if (s === "failed") return <XCircle size={14} className="text-red-500 shrink-0" />;
  return <Clock size={14} className="text-gray-400 shrink-0" />;
}

function jobStatusPill(s: JobState["status"]) {
  const base = "text-xs px-2 py-0.5 rounded-full font-medium";
  if (s === "running") return <span className={cn(base, "bg-blue-50 text-blue-700")}>Running</span>;
  if (s === "done") return <span className={cn(base, "bg-green-50 text-green-700")}>Completed</span>;
  if (s === "failed") return <span className={cn(base, "bg-red-50 text-red-600")}>Failed</span>;
  return <span className={cn(base, "bg-gray-100 text-gray-500")}>Queued</span>;
}

function formatTs(ts: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("en-KE", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
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
    <div className="border-b last:border-0 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => setExpanded((v) => !v)}>
      <div className="flex items-center gap-3 px-4 py-3">
        {jobStatusIcon(job.status)}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <FileText size={13} className="text-gray-400 shrink-0" />
            <span className="text-sm font-medium text-gray-800 truncate">{job.filename || job.s3_key}</span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{job.s3_key}</p>
        </div>
        <div className="hidden sm:flex items-center gap-6 text-xs text-gray-400 shrink-0">
          <span title="Started">{formatTs(job.started_at)}</span>
          <span title="Duration">{formatDuration(job.duration_s)}</span>
        </div>
        {jobStatusPill(job.status)}
      </div>
      {expanded && (
        <div className="px-4 pb-3 pt-0 ml-5">
          {job.error && <p className="text-xs text-red-600 mb-2 font-mono">{job.error}</p>}
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
                  <p className="text-sm font-semibold text-gray-700 mt-0.5">{val ?? "—"}</p>
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

function IngestionTab() {
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

      {/* Summary cards */}
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

// ── Verify tab ─────────────────────────────────────────────────────────────────

function VerifyRow({ activity }: { activity: VerificationActivity }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {activity.authentic ? (
          <ShieldCheck size={15} className="text-green-500 shrink-0" />
        ) : (
          <ShieldX size={15} className="text-red-500 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">
            {activity.filename || "Unnamed document"}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {activity.document_type.replace("_", " ")}
            {activity.case_number ? ` · ${activity.case_number}` : ""}
            {" · "}
            {Math.round(activity.confidence * 100)}% confidence
            {" · "}
            {formatDate(activity.created_at)}
          </p>
        </div>

        <span
          className={cn(
            "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
            activity.authentic ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
          )}
        >
          {activity.authentic ? "Authentic" : "Suspect"}
        </span>

        {expanded ? (
          <ChevronUp size={15} className="text-gray-400 shrink-0" />
        ) : (
          <ChevronDown size={15} className="text-gray-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-1">
          <VerificationReportCard report={activity.report} />
        </div>
      )}
    </div>
  );
}

function VerifyTab() {
  const { activities, loading, error } = useVerifyHistory();

  return (
    <div className="flex-1 overflow-auto px-4 py-6 max-w-4xl mx-auto w-full">
      <p className="text-sm text-gray-500 mb-5">
        Every document authentication run is saved here for audit and review.
      </p>

      <div className="bg-white border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading verifications…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-red-400">
            <XCircle size={32} className="mb-3 opacity-50" />
            <p className="text-sm">{error}</p>
          </div>
        ) : activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <ShieldCheck size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No verifications yet. Use Sheria Verify to authenticate a document.</p>
          </div>
        ) : (
          activities.map((a) => <VerifyRow key={a.id} activity={a} />)
        )}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const [activeTab, setActiveTab] = useState<Tab>("chat");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header + tab bar */}
      <div className="shrink-0 border-b bg-white px-6 pt-5 pb-0">
        <h1 className="text-xl font-bold mb-3" style={{ color: "#1a3a6b" }}>
          Activity History
        </h1>
        <div className="flex gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors",
                activeTab === id
                  ? "border-[#1a3a6b] text-[#1a3a6b]"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              )}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === "chat" && <ChatTab />}
        {activeTab === "ingestion" && <IngestionTab />}
        {activeTab === "verify" && <VerifyTab />}
      </div>
    </div>
  );
}
