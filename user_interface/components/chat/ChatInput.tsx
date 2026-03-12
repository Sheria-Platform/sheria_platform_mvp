"use client";

import { useState, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

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
    <div className="border-t bg-white px-4 py-3">
      <div className="flex gap-2 items-end max-w-4xl mx-auto">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask a legal research question… (Enter to send, Shift+Enter for new line)"
          className="flex-1 resize-none min-h-[44px] max-h-36 text-sm"
          rows={1}
          disabled={disabled || isStreaming}
        />
        {isStreaming ? (
          <Button
            onClick={onStop}
            variant="destructive"
            size="sm"
            className="shrink-0"
          >
            Stop
          </Button>
        ) : (
          <Button
            onClick={handleSend}
            size="sm"
            className="shrink-0"
            style={{ backgroundColor: "#1a3a6b" }}
            disabled={!value.trim() || disabled}
          >
            Send
          </Button>
        )}
      </div>
      <p className="text-xs text-gray-400 text-center mt-1">
        AI may make mistakes. Always verify citations with authoritative sources.
      </p>
    </div>
  );
}
