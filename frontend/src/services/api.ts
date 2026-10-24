import type {
  ChatMessage,
  ChatResponse,
  ChatSession,
  DatabaseSchema,
  SQLRunResponse,
} from '../types/chat';

const apiBase = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
const CLIENT_ID_STORAGE_KEY = 'querydesk.client-id.v1';

function getClientId(): string {
  if (typeof window === 'undefined') return 'server-rendered-client';
  const stored = localStorage.getItem(CLIENT_ID_STORAGE_KEY);
  if (stored) return stored;
  const clientId = crypto.randomUUID();
  localStorage.setItem(CLIENT_ID_STORAGE_KEY, clientId);
  return clientId;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      'X-Client-ID': getClientId(),
      ...(options?.headers || {}),
    },
  });
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
  sessionId?: string,
) {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      message,
      history: history.slice(-30).map(({ role, content, sql }) => ({ role, content, sql })),
      previous_sql: previousSql,
      session_id: sessionId,
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

export async function listSessions(): Promise<ChatSession[]> {
  const body = await request<{ sessions: ChatSession[] }>('/sessions');
  return Array.isArray(body.sessions) ? body.sessions : [];
}

export function syncSession(session: ChatSession): Promise<ChatSession> {
  return request<ChatSession>(`/sessions/${encodeURIComponent(session.id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(session),
  });
}

export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}
