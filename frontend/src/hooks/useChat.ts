import { useEffect, useRef, useState } from 'react';
import { runSQL as runSQLRequest, sendMessage } from '../services/api';
import type { ChatMessage, ChatResponse } from '../types/chat';

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedResponse, setSelectedResponse] = useState<ChatResponse | null>(null);
  const [sqlRunning, setSqlRunning] = useState(false);
  const previousSql = useRef<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const editorRequest = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      activeRequest.current?.abort();
      editorRequest.current?.abort();
    },
    [],
  );

  async function send(text: string) {
    const message = text.trim();
    if (!message || activeRequest.current || editorRequest.current) return;
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

  async function runSql(sql: string) {
    const statement = sql.trim();
    if (!statement || activeRequest.current || editorRequest.current) return;
    const controller = new AbortController();
    editorRequest.current = controller;
    setSqlRunning(true);
    setError(null);
    try {
      const result = await runSQLRequest(statement, controller.signal);
      if (controller.signal.aborted) return;
      const response: ChatResponse = {
        status: 'success',
        intent: 'query',
        generated_sql: result.sql,
        previous_sql: result.sql,
        is_valid: true,
        error_msg: null,
        retry_count: 0,
        explanation: 'Executed the validated SQL from the editor.',
        original_error: null,
        optimization_tips: [],
        query_results: result.query_results,
      };
      previousSql.current = result.sql;
      setSelectedResponse(response);
    } catch (failure) {
      if (!controller.signal.aborted) {
        const message =
          failure instanceof Error ? failure.message : 'SQL execution failed. Please try again.';
        setError(message);
        throw failure;
      }
    } finally {
      if (editorRequest.current === controller) {
        editorRequest.current = null;
        setSqlRunning(false);
      }
    }
  }

  function reset() {
    activeRequest.current?.abort();
    editorRequest.current?.abort();
    activeRequest.current = null;
    editorRequest.current = null;
    previousSql.current = null;
    setMessages([]);
    setSelectedResponse(null);
    setError(null);
    setLoading(false);
    setSqlRunning(false);
  }

  return {
    messages,
    loading,
    error,
    selectedResponse,
    sqlRunning,
    setSelectedResponse,
    send,
    runSql,
    reset,
  };
}
