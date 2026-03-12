"use client";

import { useCallback, useRef } from "react";
import { useChatStore } from "@/store/chatStore";
import { apiStream } from "@/lib/api";
import { readNDJSONStream } from "@/lib/stream";

export function useChat() {
  const store = useChatStore();
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      if (store.isStreaming || !content.trim()) return;

      let sessionId = store.activeSessionId;
      if (!sessionId) {
        sessionId = store.createSession();
      }

      store.addUserMessage(sessionId, content);
      const assistantMsgId = store.addAssistantMessage(sessionId);
      store.setStreaming(true, assistantMsgId);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await apiStream(
          "/api/v1/chat/stream",
          { message: content, session_id: sessionId },
          controller.signal
        );

        for await (const event of readNDJSONStream(response, controller.signal)) {
          if (event.event === "status" && event.step) {
            // Update pipeline step status — handled by store shape
          } else if (event.event === "answer" && event.content) {
            store.appendToMessage(sessionId!, assistantMsgId, event.content);
          } else if (event.event === "done") {
            break;
          } else if (event.event === "error") {
            store.appendToMessage(
              sessionId!,
              assistantMsgId,
              "\n\n*An error occurred. Please try again.*"
            );
            break;
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          store.appendToMessage(
            sessionId!,
            assistantMsgId,
            "\n\n*Connection error. Please check your network.*"
          );
        }
      } finally {
        store.completeMessage(sessionId!, assistantMsgId);
        store.setStreaming(false);
        abortRef.current = null;
      }
    },
    [store]
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { sendMessage, stopStream };
}
