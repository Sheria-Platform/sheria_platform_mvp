"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { MessageSquare, Layers, ShieldCheck, TrendingUp } from "lucide-react";
import { ChatTab } from "@/components/history/ChatTab";
import { IngestionTab } from "@/components/history/IngestionTab";
import { VerifyTab } from "@/components/history/VerifyTab";
import { PredictTab } from "@/components/history/PredictTab";

type Tab = "chat" | "ingestion" | "verify" | "predict";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "chat",      label: "Chat History",   icon: MessageSquare },
  { id: "ingestion", label: "Ingestion Jobs", icon: Layers },
  { id: "verify",    label: "Verifications",  icon: ShieldCheck },
  { id: "predict",   label: "Predictions",    icon: TrendingUp },
];

export default function HistoryPage() {
  const [activeTab, setActiveTab] = useState<Tab>("chat");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="shrink-0 border-b bg-white px-6 pt-5 pb-0">
        <h1 className="text-xl font-bold mb-3 text-judicial-navy">Activity History</h1>
        <div className="flex gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors",
                activeTab === id
                  ? "border-judicial-navy text-judicial-navy"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              )}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {activeTab === "chat"      && <ChatTab />}
        {activeTab === "ingestion" && <IngestionTab />}
        {activeTab === "verify"    && <VerifyTab />}
        {activeTab === "predict"   && <PredictTab />}
      </div>
    </div>
  );
}
