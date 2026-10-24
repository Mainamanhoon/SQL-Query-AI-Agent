import type { ChatMessage, ChatResponse, DatabaseSchema, SQLRunResponse } from '../types/chat';

const apiBase = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      typeof body?.detail === 'string'
        ? body.detail
        : 'The request could not be completed. Please try again.',
    );
  }
  return body as T;
}

export function sendMessage(
  message: string,
  history: ChatMessage[],
  previousSql: string | null,
  signal: AbortSignal,
) {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      message,
      history: history.slice(-30).map(({ role, content, sql }) => ({ role, content, sql })),
      previous_sql: previousSql,
    }),
  });
}

export function getSchema() {
  return request<DatabaseSchema>('/schema');
}

export function getHealth() {
  return request<{ status: string; model_configured: boolean }>('/health');
}

export function runSQL(sql: string, signal?: AbortSignal) {
  return request<SQLRunResponse>('/run-sql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({ sql }),
  });
}
