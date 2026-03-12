"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const NAV_ITEMS = [
  { href: "/chat", label: "Legal Research", icon: "💬" },
  { href: "/upload", label: "Upload Documents", icon: "📄" },
  { href: "/health", label: "System Status", icon: "🟢" },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession } =
    useChatStore();

  return (
    <aside className="w-60 text-white flex flex-col shrink-0" style={{ backgroundColor: "#1a3a6b" }}>
      {/* Logo */}
      <div className="h-14 flex items-center px-4 shrink-0">
        <span className="font-bold text-lg tracking-tight">⚖️ Sheria</span>
      </div>

      <Separator className="opacity-20" />

      {/* Nav */}
      <nav className="px-2 py-3 space-y-1 shrink-0">
        {NAV_ITEMS.map((item) => (
          <Link key={item.href} href={item.href}>
            <span
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors cursor-pointer",
                pathname === item.href
                  ? "bg-white/20 font-medium"
                  : "hover:bg-white/10 text-blue-100"
              )}
            >
              <span>{item.icon}</span>
              {item.label}
            </span>
          </Link>
        ))}
      </nav>

      <Separator className="opacity-20 mx-2" />

      {/* Session history */}
      <div className="px-3 py-2 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-blue-200 font-medium uppercase tracking-wider">
            Research Sessions
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 text-blue-200 hover:text-white hover:bg-white/10"
            onClick={() => createSession()}
            title="New session"
          >
            +
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1 px-2">
        <div className="space-y-1 pb-4">
          {sessions.slice(0, 20).map((sess) => (
            <div
              key={sess.id}
              className={cn(
                "group flex items-center gap-1 px-2 py-1.5 rounded-md text-xs cursor-pointer transition-colors",
                sess.id === activeSessionId
                  ? "bg-white/20 text-white"
                  : "text-blue-200 hover:bg-white/10 hover:text-white"
              )}
              onClick={() => setActiveSession(sess.id)}
            >
              <span className="flex-1 truncate">{sess.title}</span>
              <button
                className="opacity-0 group-hover:opacity-100 text-blue-300 hover:text-white"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(sess.id);
                }}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="text-xs text-blue-300 px-2 py-1">
              No sessions yet
            </p>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
