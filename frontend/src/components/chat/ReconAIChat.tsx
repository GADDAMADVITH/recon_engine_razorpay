import { MessageCircle, RefreshCw, Send, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, ApiClientError } from "../../api/client";
import { useChatOrder } from "../../context/ChatOrderContext";
import { cn } from "../../utils/format";

const CONSOLE_SUGGESTED_PROMPTS = [
  "Why is ORD_0002 unreconciled?",
  "Show me the main exceptions",
  "Explain ORD_0033",
  "How does reconciliation work?",
] as const;

const LANDING_SUGGESTED_PROMPTS = [
  "What is ReconEngine?",
  "How does the demo work?",
  "Explain reconciliation",
] as const;

const LANDING_WELCOME =
  "Hi — I'm ReconEngine AI. Ask me about reconciliation, the platform, or the demo.";

const CONSOLE_WELCOME =
  "Ask about your reconciliation data, exceptions, and financial operations.";

type ChatRole = "user" | "assistant" | "error";
export type ReconAIChatVariant = "console" | "landing";

interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ReconAIChat({ variant = "console" }: { variant?: ReconAIChatVariant }) {
  const location = useLocation();
  const isLanding = variant === "landing";
  const chatOrder = useChatOrder();
  const orderId = isLanding ? null : chatOrder.orderId;
  const orderResult = isLanding ? null : chatOrder.orderResult;

  const titleId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastFailed, setLastFailed] = useState<string | null>(null);

  const suggestedPrompts = isLanding ? LANDING_SUGGESTED_PROMPTS : CONSOLE_SUGGESTED_PROMPTS;
  const welcomeText = isLanding ? LANDING_WELCOME : CONSOLE_WELCOME;
  const subtitle = isLanding
    ? "Ask about the platform and demo"
    : "Your reconciliation assistant";
  const placeholder = isLanding
    ? "Ask about ReconEngine, reconciliation, or the demo..."
    : "Ask about orders, exceptions, settlements...";
  const closedLabel = isLanding ? "Ask ReconEngine AI" : "ReconEngine AI";
  const closedLabelMobile = isLanding ? "Ask AI" : "AI";

  useEffect(() => {
    if (!open) return;
    const node = listRef.current;
    if (node && typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    } else if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages, loading, open]);

  useEffect(() => {
    if (open) {
      window.setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const sendMessage = async (raw: string) => {
    const message = raw.trim();
    if (!message || loading) return;

    setInput("");
    setLastFailed(null);
    setMessages((prev) => [...prev, { id: newId(), role: "user", text: message }]);
    setLoading(true);

    try {
      const response = await api.chat({
        message,
        order_id: orderId,
        order_result: orderResult,
        page_context: isLanding
          ? {
              page: "landing",
              mode: "product_information",
            }
          : {
              page: location.pathname,
              source: orderResult ? "drawer" : "console",
            },
      });
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "assistant", text: response.message },
      ]);
    } catch (err) {
      const detail =
        err instanceof ApiClientError
          ? err.message
          : "Unable to reach ReconEngine AI right now.";
      setLastFailed(message);
      setMessages((prev) => [...prev, { id: newId(), role: "error", text: detail }]);
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void sendMessage(input);
  };

  return (
    <div
      className={cn(
        "pointer-events-none fixed z-[60] flex flex-col items-end gap-3",
        isLanding ? "bottom-5 right-4 sm:bottom-7 sm:right-7" : "bottom-5 right-5 sm:bottom-6 sm:right-6",
      )}
    >
      {open ? (
        <section
          className="pointer-events-auto flex h-[min(560px,calc(100vh-7.5rem))] w-[min(100vw-1.5rem,380px)] flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-[0_1px_0_rgba(11,27,43,0.04),0_24px_64px_rgba(11,27,43,0.14)]"
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          data-testid="recon-ai-chat-panel"
          data-variant={variant}
        >
          <header className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3.5">
            <div className="min-w-0">
              <p id={titleId} className="text-[15px] font-semibold tracking-tight text-[var(--color-ink)]">
                ReconEngine AI
              </p>
              <p className="mt-0.5 text-[12px] text-[var(--color-muted)]">{subtitle}</p>
              {orderId ? (
                <p className="mt-1.5 truncate text-[11px] font-medium text-[var(--color-accent)]">
                  Context: {orderId}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-muted)] transition hover:border-[var(--color-accent)]/30 hover:text-[var(--color-ink)]"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.length === 0 ? (
              <div className="space-y-3">
                <p className="text-sm leading-relaxed text-[var(--color-muted)]">{welcomeText}</p>
                <div className="flex flex-col gap-2">
                  {suggestedPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      disabled={loading}
                      onClick={() => void sendMessage(prompt)}
                      className="rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-left text-[13px] text-[var(--color-ink)] transition hover:border-[var(--color-accent)]/35 hover:bg-[rgba(37,99,235,0.03)] disabled:opacity-50"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed",
                  msg.role === "user" &&
                    "ml-auto bg-gradient-to-r from-[#2563EB] to-[#0891B2] text-white",
                  msg.role === "assistant" &&
                    "mr-auto border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-ink)]",
                  msg.role === "error" &&
                    "mr-auto border border-[var(--color-danger)]/25 bg-[var(--color-danger)]/5 text-[var(--color-danger)]",
                )}
              >
                <p className="whitespace-pre-wrap">{msg.text}</p>
                {msg.role === "error" && lastFailed ? (
                  <button
                    type="button"
                    className="mt-2 inline-flex items-center gap-1.5 text-[12px] font-medium underline-offset-2 hover:underline"
                    onClick={() => void sendMessage(lastFailed)}
                    disabled={loading}
                  >
                    <RefreshCw className="h-3 w-3" />
                    Retry
                  </button>
                ) : null}
              </div>
            ))}

            {loading ? (
              <div
                className="mr-auto inline-flex items-center gap-1.5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3.5 py-2.5"
                data-testid="recon-ai-typing"
                aria-live="polite"
              >
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
                <span
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-cyan)]"
                  style={{ animationDelay: "150ms" }}
                />
                <span
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent)]"
                  style={{ animationDelay: "300ms" }}
                />
                <span className="sr-only">ReconEngine AI is typing</span>
              </div>
            ) : null}
          </div>

          <form
            onSubmit={onSubmit}
            className="border-t border-[var(--color-border)] bg-white px-3 py-3"
          >
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                disabled={loading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage(input);
                  }
                }}
                placeholder={placeholder}
                className="max-h-28 min-h-[42px] flex-1 resize-none rounded-xl border border-[var(--color-border)] bg-white px-3 py-2.5 text-[13px] text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:border-[var(--color-accent)] focus:outline-none disabled:opacity-60"
                aria-label="Chat message"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="inline-flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-[#2563EB] to-[#0891B2] text-white shadow-[0_6px_16px_rgba(37,99,235,0.28)] transition hover:brightness-105 disabled:opacity-40"
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <button
        type="button"
        data-testid="recon-ai-chat-button"
        aria-label={open ? "Close ReconEngine AI chat" : "Ask ReconEngine AI"}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="pointer-events-auto inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-[#2563EB] to-[#0891B2] px-4 py-3 text-sm font-medium text-white shadow-[0_10px_28px_rgba(37,99,235,0.32)] transition hover:brightness-105 active:scale-[0.98]"
      >
        {open ? <X className="h-4 w-4" aria-hidden /> : <MessageCircle className="h-4 w-4" aria-hidden />}
        <span className="hidden sm:inline">{open ? "Close" : closedLabel}</span>
        <span className="sm:hidden">{open ? "Close" : closedLabelMobile}</span>
      </button>
    </div>
  );
}
