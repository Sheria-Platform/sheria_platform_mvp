"use client";

import { useEffect, useRef } from "react";
import { ChatMessage } from "@/types/chat";
import { UserMessage } from "./UserMessage";
import { AssistantMessage } from "./AssistantMessage";
import { ScrollArea } from "@/components/ui/scroll-area";

interface MessageListProps {
  messages: ChatMessage[];
  sessionId: string;
  onRerun?: (comment: string) => void;
}

export function MessageList({ messages, sessionId, onRerun }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <ScrollArea className="flex-1 overflow-y-auto">
      <div className="py-4 space-y-2 max-w-3xl mx-auto px-4">
        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserMessage key={msg.id} message={msg} />
          ) : (
            <AssistantMessage key={msg.id} message={msg} sessionId={sessionId} onRerun={onRerun} />
          )
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
