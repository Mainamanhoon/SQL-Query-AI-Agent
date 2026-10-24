import { useEffect, useRef, useState } from 'react';
import { runSQL as runSQLRequest, sendMessage } from '../services/api';
import type { ChatMessage, ChatResponse, ChatSession } from '../types/chat';

const SESSION_STORAGE_KEY = 'querydesk.sessions.v1';
const MAX_SESSIONS = 20;
const MAX_STORED_MESSAGES = 60;

interface SessionState {
  sessions: ChatSession[];
  activeSessionId: string;
}

function createSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: 'New conversation',
    createdAt: now,
    updatedAt: now,
    messages: [],
    previousSql: null,
    selectedResponse: null,
  };
}

function validSessions(value: unknown): ChatSession[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (session): session is ChatSession =>
        Boolean(session) &&
        typeof session === 'object' &&
        typeof (session as ChatSession).id === 'string' &&
        Array.isArray((session as ChatSession).messages),
    )
    .slice(0, MAX_SESSIONS);
}

function readStoredState(): SessionState | null {
  if (typeof window === 'undefined') return null;
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || '[]');
    const sessions = Array.isArray(parsed)
      ? validSessions(parsed)
      : validSessions((parsed as { sessions?: unknown }).sessions);
    if (!sessions.length) return null;
    const requestedActiveId =
      !Array.isArray(parsed) &&
      typeof (parsed as { activeSessionId?: unknown }).activeSessionId === 'string'
        ? (parsed as { activeSessionId: string }).activeSessionId
        : null;
    return {
      sessions,
      activeSessionId:
        sessions.find((session) => session.id === requestedActiveId)?.id || sessions[0].id,
    };
  } catch {
    return null;
  }
}

function initialSessionState(): SessionState {
  const stored = readStoredState();
  if (stored) return stored;
  const initialSession = createSession();
  return {
    sessions: [initialSession],
    activeSessionId: initialSession.id,
  };
}

function titleFromMessage(message: string): string {
  const title = message.replace(/\s+/g, ' ').trim();
  return title.length > 42 ? `${title.slice(0, 42).trimEnd()}…` : title;
}

export function useChat() {
  const [sessionState, setSessionState] = useState<SessionState>(initialSessionState);
  const [loading, setLoading] = useState(false);
  const [sqlRunning, setSqlRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const editorRequest = useRef<AbortController | null>(null);

  const activeSession =
    sessionState.sessions.find((session) => session.id === sessionState.activeSessionId) ||
    sessionState.sessions[0];
  const messages = activeSession?.messages || [];
  const selectedResponse = activeSession?.selectedResponse || null;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(
        SESSION_STORAGE_KEY,
        JSON.stringify({
          activeSessionId: sessionState.activeSessionId,
          sessions: sessionState.sessions.map((session) => ({
            ...session,
            messages: session.messages.slice(-MAX_STORED_MESSAGES),
          })),
        }),
      );
    } catch {
      // A full or disabled browser storage should not prevent the chat from working.
    }
  }, [sessionState.activeSessionId, sessionState.sessions]);

  useEffect(() => () => {
    activeRequest.current?.abort();
    editorRequest.current?.abort();
  }, []);

  function updateSession(
    sessionId: string,
    updater: (session: ChatSession) => ChatSession,
  ): void {
    setSessionState((current) => ({
      ...current,
      sessions: current.sessions.map((session) =>
        session.id === sessionId ? updater(session) : session,
      ),
    }));
  }

  function cancelRequests(): void {
    activeRequest.current?.abort();
    editorRequest.current?.abort();
    activeRequest.current = null;
    editorRequest.current = null;
    setLoading(false);
    setSqlRunning(false);
  }

  async function send(text: string): Promise<void> {
    const message = text.trim();
    if (!message || activeRequest.current || editorRequest.current || !activeSession) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    const sessionId = activeSession.id;
    const newMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: message };
    updateSession(sessionId, (session) => ({
      ...session,
      title: session.messages.length ? session.title : titleFromMessage(message),
      updatedAt: new Date().toISOString(),
      messages: [...session.messages, newMessage],
    }));
    setLoading(true);
    setError(null);
    try {
      const response = await sendMessage(
        message,
        activeSession.messages,
        activeSession.previousSql,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      const nextPreviousSql =
        response.status === 'success' && response.generated_sql
          ? response.generated_sql
          : activeSession.previousSql;
      updateSession(sessionId, (session) => ({
        ...session,
        updatedAt: new Date().toISOString(),
        previousSql: nextPreviousSql,
        selectedResponse: response,
        messages: [
          ...session.messages,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: response.explanation,
            sql: response.generated_sql || undefined,
            response,
          },
        ],
      }));
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(
          failure instanceof Error ? failure.message : 'Connection interrupted. Please try again.',
        );
        updateSession(sessionId, (session) => ({
          ...session,
          messages: session.messages.filter((item) => item.id !== newMessage.id),
        }));
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }

  async function runSql(sql: string): Promise<void> {
    const statement = sql.trim();
    if (!statement || activeRequest.current || editorRequest.current || !activeSession) return;
    const controller = new AbortController();
    editorRequest.current = controller;
    const sessionId = activeSession.id;
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
      updateSession(sessionId, (session) => ({
        ...session,
        updatedAt: new Date().toISOString(),
        previousSql: result.sql,
        selectedResponse: response,
      }));
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

  function selectSession(sessionId: string): void {
    if (!sessionState.sessions.some((session) => session.id === sessionId)) return;
    cancelRequests();
    setError(null);
    setSessionState((current) => ({ ...current, activeSessionId: sessionId }));
  }

  function newSession(): void {
    cancelRequests();
    const session = createSession();
    setError(null);
    setSessionState((current) => ({
      activeSessionId: session.id,
      sessions: [session, ...current.sessions].slice(0, MAX_SESSIONS),
    }));
  }

  function setSelectedResponse(response: ChatResponse): void {
    if (!activeSession) return;
    updateSession(activeSession.id, (session) => ({ ...session, selectedResponse: response }));
  }

  function reset(): void {
    newSession();
  }

  return {
    messages,
    loading,
    error,
    selectedResponse,
    sqlRunning,
    sessions: sessionState.sessions,
    activeSessionId: sessionState.activeSessionId,
    setSelectedResponse,
    selectSession,
    newSession,
    send,
    runSql,
    reset,
  };
}
