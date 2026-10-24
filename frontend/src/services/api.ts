import type {
  ChatMessage,
  ChatResponse,
  ChatSession,
  DatabaseSchema,
  SQLDialect,
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

async function streamRequest(
  path: string,
  options: RequestInit,
  onChunk: (text: string) => void,
): Promise<ChatResponse> {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      'X-Client-ID': getClientId(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === 'string'
        ? body.detail
        : 'The streaming request could not be completed. Please try again.',
    );
  }
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('text/event-stream')) {
    return (await response.json()) as ChatResponse;
  }
  if (!response.body) throw new Error('The browser does not support streaming responses.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResponse: ChatResponse | null = null;

  function consume(frame: string): void {
    let eventName = 'message';
    const dataLines: string[] = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join('\n')) as {
      text?: string;
      response?: ChatResponse;
      detail?: string;
    };
    if (eventName === 'chunk' && data.text) onChunk(data.text);
    if (eventName === 'error') throw new Error(data.detail || 'The streaming request failed.');
    if (eventName === 'complete' && data.response) finalResponse = data.response;
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';
    for (const frame of frames) consume(frame);
    if (done) break;
  }
  if (buffer.trim()) consume(buffer);
  if (!finalResponse) throw new Error('The streaming response ended before completion.');
  return finalResponse;
}

export function sendMessage(
  message: string,
  history: ChatMessage[],
  previousSql: string | null,
  signal: AbortSignal,
  sessionId?: string,
) {
  return streamRequest('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      message,
      history: history.slice(-30).map(({ role, content, sql }) => ({ role, content, sql })),
      previous_sql: previousSql,
      session_id: sessionId,
    }),
  }, () => undefined);
}

export function sendMessageStream(
  message: string,
  history: ChatMessage[],
  previousSql: string | null,
  signal: AbortSignal,
  sessionId: string | undefined,
  onChunk: (text: string) => void,
): Promise<ChatResponse> {
  return streamRequest(
    '/chat/stream',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        message,
        history: history.slice(-30).map(({ role, content, sql }) => ({ role, content, sql })),
        previous_sql: previousSql,
        session_id: sessionId,
      }),
    },
    onChunk,
  );
}

export function getSchema() {
  return request<DatabaseSchema>('/schema');
}

export function getHealth() {
  return request<{ status: string; model_configured: boolean }>('/health');
}

export function runSQL(sql: string, dialect: SQLDialect = 'sqlite', signal?: AbortSignal) {
  return request<SQLRunResponse>('/run-sql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify(dialect === 'sqlite' ? { sql } : { sql, dialect }),
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
