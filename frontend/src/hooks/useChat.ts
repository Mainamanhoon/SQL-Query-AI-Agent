import { useEffect, useRef, useState } from 'react';
import { sendMessage } from '../services/api';
import type { ChatMessage, ChatResponse } from '../types/chat';

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedResponse, setSelectedResponse] = useState<ChatResponse | null>(null);
  const previousSql = useRef<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function send(text: string) {
    const message = text.trim();
    if (!message || activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    const newMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: message };
    setMessages((current) => [...current, newMessage]);
    setLoading(true);
    setError(null);
    try {
      const response = await sendMessage(message, messages, previousSql.current, controller.signal);
      if (controller.signal.aborted) return;
      if (response.status === 'success' && response.generated_sql) {
        previousSql.current = response.generated_sql;
      }
      setSelectedResponse(response);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.explanation,
          sql: response.generated_sql || undefined,
          response,
        },
      ]);
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(
          failure instanceof Error ? failure.message : 'Connection interrupted. Please try again.',
        );
        setMessages((current) => current.filter((item) => item.id !== newMessage.id));
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }

  function reset() {
    activeRequest.current?.abort();
    activeRequest.current = null;
    previousSql.current = null;
    setMessages([]);
    setSelectedResponse(null);
    setError(null);
    setLoading(false);
  }

  return { messages, loading, error, selectedResponse, setSelectedResponse, send, reset };
}
