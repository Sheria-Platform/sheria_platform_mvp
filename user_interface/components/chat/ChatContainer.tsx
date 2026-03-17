"use client";

import { useChatStore, getActiveSession } from "@/store/chatStore";
import { useChat } from "@/hooks/useChat";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { EmptyState } from "./EmptyState";

export function ChatContainer() {
  const store = useChatStore();
  const activeSession = useChatStore(getActiveSession);
  const { sendMessage, stopStream } = useChat();

  async function handleSend(text: string) {
    await sendMessage(text);
  }

  return (
    <div className="flex flex-col h-full">
      {!activeSession || activeSession.messages.length === 0 ? (
        <div className="flex-1 overflow-auto">
          <EmptyState
            onSelect={(q) => {
              if (!store.activeSessionId) store.createSession();
              handleSend(q);
            }}
          />
        </div>
      ) : (
        <MessageList
          messages={activeSession.messages}
          sessionId={activeSession.id}
        />
      )}
      <ChatInput
        onSend={handleSend}
        onStop={stopStream}
        isStreaming={store.isStreaming}
      />
    </div>
  );
}
