"use client";

import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { useHistory } from "@/hooks/useHistory";
import { SessionSummary, MessageRecord } from "@/types/api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { History, MessageSquare, ArrowRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-KE", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

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
      <p
        className={cn(
          "text-sm font-medium leading-snug line-clamp-2",
          active ? "text-white" : "text-gray-800"
        )}
      >
        {session.preview || "Empty session"}
      </p>
      <div
        className={cn(
          "flex items-center justify-between mt-1.5",
          active ? "text-gray-300" : "text-gray-400"
        )}
      >
        <span className="text-xs">{formatDate(session.last_activity)}</span>
        <span
          className={cn(
            "text-xs px-1.5 py-0.5 rounded-full",
            active ? "bg-white/20" : "bg-gray-100"
          )}
        >
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
          <p className="text-xs text-gray-400 text-right mt-1">
            {formatDate(message.created_at)}
          </p>
        </div>
      ) : (
        <div className="max-w-[85%]">
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
            <div className="prose prose-sm prose-slate max-w-none text-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeSanitize]}
              >
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

export default function HistoryPage() {
  const router = useRouter();
  const { setActiveSession } = useChatStore();
  const { sessions, loading, selectedId, messages, messagesLoading, selectSession } =
    useHistory();

  function handleLoadInChat() {
    if (!selectedId) return;
    setActiveSession(selectedId);
    router.push("/chat");
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Sessions list ── */}
      <div className="w-72 shrink-0 border-r bg-gray-50 flex flex-col">
        <div className="px-4 py-4 border-b bg-white shrink-0">
          <div className="flex items-center gap-2">
            <History size={16} className="text-gray-500" />
            <h2 className="text-sm font-semibold text-gray-800">Chat History</h2>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">Past research sessions</p>
        </div>

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

      {/* ── Message thread ── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        {selectedId ? (
          <>
            {/* Thread header */}
            <div className="px-6 py-3 border-b bg-white shrink-0 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-800 truncate max-w-md">
                  {sessions.find((s) => s.session_id === selectedId)?.preview ||
                    "Session"}
                </p>
                <p className="text-xs text-gray-400">
                  {sessions.find((s) => s.session_id === selectedId)?.message_count ?? 0}{" "}
                  messages · read-only
                </p>
              </div>
              <Button
                size="sm"
                onClick={handleLoadInChat}
                className="gap-1.5 text-xs h-8"
              >
                Continue in Chat
                <ArrowRight size={13} />
              </Button>
            </div>

            {/* Messages */}
            <ScrollArea className="flex-1 py-4">
              {messagesLoading ? (
                <div className="space-y-4 px-4">
                  {[...Array(4)].map((_, i) => (
                    <div
                      key={i}
                      className={cn("flex", i % 2 === 0 ? "justify-end" : "justify-start")}
                    >
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
