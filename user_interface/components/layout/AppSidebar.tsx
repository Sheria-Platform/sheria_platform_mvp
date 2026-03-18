"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useChatStore } from "@/store/chatStore";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { clearAuth } from "@/lib/auth";
import { RoleBadge } from "./RoleBadge";
import { UserRole } from "@/types/api";
import {
  MessageSquarePlus,
  FileText,
  Activity,
  LogOut,
  History,
  Users,
  ShieldCheck,
  TrendingUp,
  PanelLeftClose,
  PanelLeftOpen,
  UserCircle,
  ListChecks,
  BarChart2,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/chat",    label: "Sheria Ask",       icon: MessageSquarePlus },
  { href: "/verify",  label: "Sheria Verify",    icon: ShieldCheck },
  { href: "/predict", label: "Sheria Predict",   icon: TrendingUp },
  { href: "/upload",  label: "Sheria Digitize",  icon: FileText },
  { href: "/jobs",    label: "Ingestion Jobs",   icon: ListChecks },
  { href: "/history", label: "Activity History", icon: History },
];

const ADMIN_ITEMS = [
  { href: "/health",            label: "System Status",    icon: Activity },
  { href: "/admin/users",       label: "User Management",  icon: Users },
  { href: "/admin/analytics",   label: "Analytics",        icon: BarChart2 },
];

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { createSession, user, setUser } = useChatStore();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    clearAuth();
    setUser(null);
    router.push("/login");
  }

  const allNavItems = [
    ...NAV_ITEMS,
    ...(user?.role === "admin" ? ADMIN_ITEMS : []),
  ];

  return (
    <TooltipProvider delay={200}>
      <aside
        className={cn(
          "bg-[#1a3a6b] text-white flex flex-col shrink-0 transition-[width] duration-200 ease-in-out overflow-hidden",
          collapsed ? "w-16" : "w-64"
        )}
      >
        {/* ── Logo + toggle ───────────────────────────────────────── */}
        <div className="h-14 flex items-center shrink-0 px-3 gap-2">
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <Image
                src="/sheria-logo.jpg"
                alt="Sheria Platform"
                width={120}
                height={32}
                className="h-8 object-contain"
                style={{ width: "auto" }}
                priority
              />
            </div>
          )}
          <button
            onClick={() => setCollapsed((v) => !v)}
            className={cn(
              "shrink-0 p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors",
              collapsed && "mx-auto"
            )}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        <Separator className="opacity-10" />

        {/* ── New chat ────────────────────────────────────────────── */}
        <div className={cn("py-3 shrink-0", collapsed ? "px-2" : "px-3")}>
          {collapsed ? (
            <Tooltip>
              <TooltipTrigger
                onClick={() => { createSession(); router.push("/chat"); }}
                className="w-full flex items-center justify-center p-2 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                <MessageSquarePlus size={18} />
              </TooltipTrigger>
              <TooltipContent side="right">New chat</TooltipContent>
            </Tooltip>
          ) : (
            <Button
              onClick={() => { createSession(); router.push("/chat"); }}
              variant="ghost"
              className="w-full justify-start gap-2 text-sm text-gray-300 hover:text-white hover:bg-white/10 rounded-lg h-9"
            >
              <MessageSquarePlus size={16} />
              New chat
            </Button>
          )}
        </div>

        <Separator className="opacity-10" />

        {/* ── Nav items ───────────────────────────────────────────── */}
        <nav className={cn("py-2 space-y-0.5 shrink-0", collapsed ? "px-2" : "px-3")}>
          {allNavItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;

            if (collapsed) {
              return (
                <Tooltip key={item.href}>
                  <TooltipTrigger render={<Link href={item.href} />}>
                    <span
                      className={cn(
                        "flex items-center justify-center p-2 rounded-lg transition-colors cursor-pointer",
                        active
                          ? "bg-white/15 text-white"
                          : "text-gray-400 hover:text-white hover:bg-white/10"
                      )}
                    >
                      <Icon size={18} />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            }

            return (
              <Link key={item.href} href={item.href}>
                <span
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer",
                    active
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

        <div className="flex-1" />

        <Separator className="opacity-10" />

        {/* ── User + logout ────────────────────────────────────────── */}
        <div className={cn("py-3 shrink-0 space-y-1", collapsed ? "px-2" : "px-3")}>
          {user && !collapsed && (
            <Link href="/profile">
              <div className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-white/10 transition-colors cursor-pointer">
                <RoleBadge role={user.role as UserRole} />
                <span className="text-xs text-gray-400 truncate flex-1">
                  {user.full_name || user.username}
                </span>
              </div>
            </Link>
          )}

          {collapsed ? (
            <>
              <Tooltip>
                <TooltipTrigger render={<Link href="/profile" />}>
                  <span className="w-full flex items-center justify-center p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors">
                    <UserCircle size={16} />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right">My Profile</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger
                  onClick={handleLogout}
                  className="w-full flex items-center justify-center p-2 rounded-lg text-gray-500 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <LogOut size={16} />
                </TooltipTrigger>
                <TooltipContent side="right">Sign out</TooltipContent>
              </Tooltip>
            </>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="w-full justify-start gap-2 text-xs text-gray-500 hover:text-white hover:bg-white/10 rounded-lg h-8"
            >
              <LogOut size={13} />
              Sign out
            </Button>
          )}
        </div>
      </aside>
    </TooltipProvider>
  );
}
