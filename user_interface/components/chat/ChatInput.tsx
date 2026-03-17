"use client";

import { useState, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { ArrowUp, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
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
      <div className="max-w-3xl mx-auto relative">
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
      <p className="text-xs text-center text-gray-400 mt-2">
        AI may make mistakes. Always verify citations with authoritative sources.
      </p>
    </div>
  );
}
