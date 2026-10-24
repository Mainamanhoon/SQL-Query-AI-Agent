import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useChat } from './useChat';
import type { ChatResponse } from '../types/chat';

const fetchMock = vi.fn<typeof fetch>();
const success: ChatResponse = {
  status: 'success',
  intent: 'query',
  generated_sql: 'SELECT name FROM Users',
  previous_sql: 'SELECT name FROM Users',
  is_valid: true,
  error_msg: null,
  retry_count: 0,
  explanation: 'Lists user names.',
  original_error: null,
  optimization_tips: [],
  query_results: {
    columns: ['name'],
    rows: [['Maya']],
    truncated: false,
    elapsed_ms: 1,
    row_limit: 200,
  },
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('conversation state', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('sends history and the previous successful SQL with follow-ups', async () => {
    fetchMock.mockImplementation(async () => response(success));
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send('Show users');
    });
    await act(async () => {
      await result.current.send('Only California');
    });
    const payload = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
    expect(payload.message).toBe('Only California');
    expect(payload.previous_sql).toBe(success.generated_sql);
    expect(payload.history).toContainEqual(
      expect.objectContaining({ role: 'assistant', sql: success.generated_sql }),
    );
    expect(result.current.messages).toHaveLength(4);
  });

  it('retains previous SQL across clarification responses', async () => {
    fetchMock
      .mockResolvedValueOnce(response(success))
      .mockResolvedValueOnce(response({ ...success, status: 'clarification', generated_sql: null }))
      .mockResolvedValueOnce(response(success));
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send('Show users');
    });
    await act(async () => {
      await result.current.send('Only active');
    });
    await act(async () => {
      await result.current.send('I mean California');
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body)).previous_sql).toBe(
      success.generated_sql,
    );
  });

  it('shows API errors and removes the failed submission from history', async () => {
    fetchMock.mockResolvedValueOnce(response({ detail: 'Model unavailable' }, 503));
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send('Show users');
    });
    expect(result.current.error).toBe('Model unavailable');
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.loading).toBe(false);
  });

  it('runs edited SQL through the guarded execution endpoint', async () => {
    const runResult = {
      sql: 'SELECT state, COUNT(*) AS user_count FROM Users GROUP BY state',
      query_results: {
        columns: ['state', 'user_count'],
        rows: [['California', 3]],
        truncated: false,
        elapsed_ms: 1,
        row_limit: 200,
      },
    };
    fetchMock.mockResolvedValueOnce(response(runResult));
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.runSql('SELECT state, COUNT(*) FROM Users GROUP BY state');
    });
    expect(fetchMock.mock.calls[0][0]).toContain('/run-sql');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      sql: 'SELECT state, COUNT(*) FROM Users GROUP BY state',
    });
    expect(result.current.selectedResponse?.query_results?.rows).toEqual([['California', 3]]);
  });

  it('ignores a stale response after starting a new conversation', async () => {
    let resolve!: (response: Response) => void;
    fetchMock.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const { result } = renderHook(() => useChat());
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.send('Show users');
    });
    act(() => result.current.reset());
    await act(async () => {
      resolve(response(success));
      await pending;
    });
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.selectedResponse).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});
