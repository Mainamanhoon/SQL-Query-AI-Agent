import { afterEach, describe, expect, it, vi } from 'vitest';
import { sendMessageStream } from './api';

describe('streaming chat transport', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('delivers explanation chunks before the final guarded response', async () => {
    const finalResponse = {
      status: 'success',
      intent: 'query',
      generated_sql: 'SELECT name FROM Users',
      previous_sql: 'SELECT name FROM Users',
      is_valid: true,
      error_msg: null,
      retry_count: 0,
      explanation: 'Lists users.',
      original_error: null,
      optimization_tips: [],
      query_results: null,
    } as const;
    const body = [
      'event: status\ndata: {"state":"processing"}\n\n',
      'event: chunk\ndata: {"text":"Lists "}\n\n',
      `event: complete\ndata: ${JSON.stringify({ response: finalResponse })}\n\n`,
    ].join('');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
      ),
    );
    const chunks: string[] = [];
    const response = await sendMessageStream(
      'Show users',
      [],
      null,
      new AbortController().signal,
      'session-1',
      (chunk) => chunks.push(chunk),
    );
    expect(chunks).toEqual(['Lists ']);
    expect(response.generated_sql).toBe('SELECT name FROM Users');
  });
});
