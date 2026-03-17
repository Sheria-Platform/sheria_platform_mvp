"use client";

import { useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { RoleBadge } from "./RoleBadge";
import { Button } from "@/components/ui/button";
import { clearAuth } from "@/lib/auth";
import { UserRole } from "@/types/api";

export function TopBar() {
  const router = useRouter();
  const user = useChatStore((s) => s.user);
  const setUser = useChatStore((s) => s.setUser);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    clearAuth();
    setUser(null);
    router.push("/login");
  }

  return (
    <header className="h-14 border-b bg-white flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-3">
        <span className="font-semibold text-sm hidden sm:block" style={{ color: "#1a3a6b" }}>
          Sheria Platform
        </span>
      </div>
      <div className="flex items-center gap-3">
        {user && <RoleBadge role={user.role as UserRole} />}
        <span className="text-sm text-gray-600 hidden sm:block">
          {user?.full_name || user?.username}
        </span>
        <Button variant="ghost" size="sm" onClick={handleLogout} className="text-gray-500">
          Sign out
        </Button>
      </div>
    </header>
  );
}
