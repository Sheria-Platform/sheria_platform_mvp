"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { ChatMessage } from "@/types/chat";
import { formatTime } from "@/lib/utils";
import { StreamingIndicator } from "./StreamingIndicator";
import { FeedbackButtons } from "./FeedbackButtons";

export function AssistantMessage({
  message,
  sessionId,
  onRerun,
}: {
  message: ChatMessage;
  sessionId: string;
  onRerun?: (comment: string, webSearch: boolean) => void;
}) {
  return (
    <div className="flex flex-col px-4 py-1 max-w-[85%]">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        {message.isStreaming && !message.content && (
          <StreamingIndicator steps={message.pipelineSteps} />
        )}
        {message.content ? (
          <div className="prose prose-sm prose-slate max-w-none text-sm">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeSanitize]}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : message.isStreaming ? (
          <div className="flex gap-1 py-1">
            <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "0ms" }} />
            <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "150ms" }} />
            <span className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        ) : null}
      </div>
      <div className="flex items-center gap-2 mt-0.5 ml-1">
        <span className="text-xs text-gray-400">{formatTime(message.timestamp)}</span>
        {!message.isStreaming && message.content && (
          <FeedbackButtons
            messageId={message.id}
            sessionId={sessionId}
            feedbackGiven={message.feedbackGiven}
            onRerun={onRerun}
          />
        )}
      </div>
    </div>
  );
}
