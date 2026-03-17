"use client";

import { useState, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { ArrowUp, Square, Globe } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  webSearchEnabled: boolean;
  onToggleWebSearch: () => void;
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
  webSearchEnabled,
  onToggleWebSearch,
}: ChatInputProps) {
  const [value, setValue] = useState("");

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="bg-[#f7f7f8] px-4 pb-4 pt-2">
      <div className="max-w-3xl mx-auto">

        {/* Textarea row — send/stop button only, no Globe overlap */}
        <div className="relative">
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask a legal research question… (Enter to send, Shift+Enter for new line)"
            className="rounded-2xl border border-gray-200 shadow-sm resize-none min-h-[52px] max-h-40 text-sm pr-12 py-3 bg-white focus-visible:ring-1 focus-visible:ring-gray-300"
            rows={1}
            disabled={disabled || isStreaming}
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="absolute right-3 bottom-3 w-8 h-8 flex items-center justify-center rounded-lg bg-red-500 hover:bg-red-600 text-white transition-colors"
              title="Stop"
            >
              <Square size={14} fill="white" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!value.trim() || disabled}
              className="absolute right-3 bottom-3 w-8 h-8 flex items-center justify-center rounded-lg bg-[#1a1a1a] hover:bg-[#333] text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title="Send"
            >
              <ArrowUp size={16} />
            </button>
          )}
        </div>

        {/* Controls row — web search toggle + disclaimer */}
        <div className="flex items-center justify-between mt-1.5 px-1">
          <button
            type="button"
            onClick={onToggleWebSearch}
            disabled={isStreaming}
            title={
              webSearchEnabled
                ? "Web search ON — click to disable"
                : "Enable live Kenya Law web search (new.kenyalaw.org)"
            }
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors",
              webSearchEnabled
                ? "bg-blue-100 text-blue-700 hover:bg-blue-200"
                : "text-gray-400 hover:text-gray-600 hover:bg-gray-100",
              isStreaming && "opacity-40 cursor-not-allowed"
            )}
          >
            <Globe size={13} />
            <span>Kenya Law</span>
          </button>

          <p className="text-xs text-gray-400">
            {webSearchEnabled ? (
              <span className="text-blue-500">Live web search active</span>
            ) : (
              "AI may make mistakes. Always verify citations."
            )}
          </p>
        </div>

      </div>
    </div>
  );
}
