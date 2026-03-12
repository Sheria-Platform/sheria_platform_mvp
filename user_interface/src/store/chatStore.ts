import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { ChatSession, ChatMessage, AuthUser } from "@/types/chat";
import { generateId } from "@/lib/utils";

interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isStreaming: boolean;
  streamingMessageId: string | null;
  user: AuthUser | null;

  // Session actions
  createSession: () => string;
  setActiveSession: (id: string) => void;
  deleteSession: (id: string) => void;

  // Message actions
  addUserMessage: (sessionId: string, content: string) => string;
  addAssistantMessage: (sessionId: string) => string;
  appendToMessage: (sessionId: string, messageId: string, chunk: string) => void;
  completeMessage: (sessionId: string, messageId: string) => void;
  setMessageFeedback: (sessionId: string, messageId: string, feedback: "thumbs_up" | "thumbs_down") => void;

  // Streaming state
  setStreaming: (value: boolean, messageId?: string) => void;

  // Auth
  setUser: (user: AuthUser | null) => void;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      isStreaming: false,
      streamingMessageId: null,
      user: null,

      createSession: () => {
        const id = generateId();
        const session: ChatSession = {
          id,
          title: "New Research Session",
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((s) => ({ sessions: [session, ...s.sessions], activeSessionId: id }));
        return id;
      },

      setActiveSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) =>
        set((s) => ({
          sessions: s.sessions.filter((sess) => sess.id !== id),
          activeSessionId: s.activeSessionId === id
            ? s.sessions.find((sess) => sess.id !== id)?.id ?? null
            : s.activeSessionId,
        })),

      addUserMessage: (sessionId, content) => {
        const id = generateId();
        const msg: ChatMessage = {
          id,
          role: "user",
          content,
          timestamp: Date.now(),
        };
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? {
                  ...sess,
                  messages: [...sess.messages, msg],
                  title: sess.messages.length === 0
                    ? content.slice(0, 60)
                    : sess.title,
                  updatedAt: Date.now(),
                }
              : sess
          ),
        }));
        return id;
      },

      addAssistantMessage: (sessionId) => {
        const id = generateId();
        const msg: ChatMessage = {
          id,
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          isStreaming: true,
          pipelineSteps: [
            { step: "planner", status: "pending" },
            { step: "retriever", status: "pending" },
            { step: "responder", status: "pending" },
          ],
        };
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? { ...sess, messages: [...sess.messages, msg], updatedAt: Date.now() }
              : sess
          ),
        }));
        return id;
      },

      appendToMessage: (sessionId, messageId, chunk) =>
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? {
                  ...sess,
                  messages: sess.messages.map((msg) =>
                    msg.id === messageId
                      ? { ...msg, content: msg.content + chunk }
                      : msg
                  ),
                }
              : sess
          ),
        })),

      completeMessage: (sessionId, messageId) =>
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? {
                  ...sess,
                  messages: sess.messages.map((msg) =>
                    msg.id === messageId
                      ? {
                          ...msg,
                          isStreaming: false,
                          pipelineSteps: msg.pipelineSteps?.map((step) => ({
                            ...step,
                            status: "complete" as const,
                          })),
                        }
                      : msg
                  ),
                }
              : sess
          ),
        })),

      setMessageFeedback: (sessionId, messageId, feedback) =>
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId
              ? {
                  ...sess,
                  messages: sess.messages.map((msg) =>
                    msg.id === messageId
                      ? { ...msg, feedbackGiven: feedback }
                      : msg
                  ),
                }
              : sess
          ),
        })),

      setStreaming: (value, messageId) =>
        set({ isStreaming: value, streamingMessageId: messageId ?? null }),

      setUser: (user) => set({ user }),
    }),
    {
      name: "sheria-chat",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        sessions: state.sessions,
        activeSessionId: state.activeSessionId,
        user: state.user,
      }),
    }
  )
);

export const getActiveSession = (state: ReturnType<typeof useChatStore.getState>) =>
  state.sessions.find((s) => s.id === state.activeSessionId) ?? null;
