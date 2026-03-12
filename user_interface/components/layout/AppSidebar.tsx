"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { clearAuth } from "@/lib/auth";
import { RoleBadge } from "./RoleBadge";
import { UserRole } from "@/types/api";
import { MessageSquarePlus, FileText, Activity, LogOut, Layers } from "lucide-react";

const NAV_ITEMS = [
  { href: "/chat", label: "Legal Research", icon: MessageSquarePlus },
  { href: "/upload", label: "Upload Documents", icon: FileText },
  { href: "/jobs", label: "Ingestion Jobs", icon: Layers },
  { href: "/health", label: "System Status", icon: Activity },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession, user, setUser } =
    useChatStore();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    clearAuth();
    setUser(null);
    router.push("/login");
  }

  return (
    <aside className="w-64 bg-[#1a1a1a] text-white flex flex-col shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 shrink-0">
        <Image
          src="/sheria-logo.jpg"
          alt="Sheria Platform"
          width={120}
          height={32}
          className="h-8 w-auto object-contain"
          priority
        />
      </div>

      <Separator className="opacity-10" />

      {/* New Chat */}
      <div className="px-3 py-3 shrink-0">
        <Button
          onClick={() => { createSession(); router.push("/chat"); }}
          variant="ghost"
          className="w-full justify-start gap-2 text-sm text-gray-300 hover:text-white hover:bg-white/10 rounded-lg h-9"
        >
          <MessageSquarePlus size={16} />
          New chat
        </Button>
      </div>

      <Separator className="opacity-10" />

      {/* Nav */}
      <nav className="px-3 py-2 space-y-0.5 shrink-0">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href}>
              <span
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer",
                  pathname === item.href
                    ? "bg-white/15 text-white font-medium"
                    : "text-gray-400 hover:text-white hover:bg-white/10"
                )}
              >
                <Icon size={15} />
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      <Separator className="opacity-10 mx-3 my-1" />

      {/* Recent sessions label */}
      <div className="px-4 pt-2 pb-1 shrink-0">
        <span className="text-xs text-gray-500 font-medium uppercase tracking-wider">
          Recent sessions
        </span>
      </div>

      {/* Session list */}
      <ScrollArea className="flex-1 px-2">
        <div className="space-y-0.5 pb-4">
          {sessions.slice(0, 20).map((sess) => (
            <div
              key={sess.id}
              className={cn(
                "group flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs cursor-pointer transition-colors",
                sess.id === activeSessionId
                  ? "bg-white/15 text-white"
                  : "text-gray-400 hover:text-white hover:bg-white/10"
              )}
              onClick={() => { setActiveSession(sess.id); router.push("/chat"); }}
            >
              <span className="flex-1 truncate">{sess.title}</span>
              <button
                className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white ml-1"
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
            <p className="text-xs text-gray-600 px-3 py-1">No sessions yet</p>
          )}
        </div>
      </ScrollArea>

      <Separator className="opacity-10" />

      {/* User section at bottom */}
      <div className="px-3 py-3 shrink-0 space-y-2">
        {user && (
          <div className="flex items-center gap-2 px-2 py-1">
            <RoleBadge role={user.role as UserRole} />
            <span className="text-xs text-gray-400 truncate flex-1">
              {user.full_name || user.username}
            </span>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleLogout}
          className="w-full justify-start gap-2 text-xs text-gray-500 hover:text-white hover:bg-white/10 rounded-lg h-8"
        >
          <LogOut size={13} />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
