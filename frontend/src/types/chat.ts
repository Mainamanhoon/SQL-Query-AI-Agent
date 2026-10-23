export type Intent = 'query' | 'optimize' | 'debug' | 'out_of_scope' | 'clarify';

export interface QueryResults {
  columns: string[];
  rows: (string | number | null)[][];
  truncated: boolean;
  elapsed_ms: number;
  row_limit: number | null;
}

export interface ChatResponse {
  status: 'success' | 'rejected' | 'clarification' | 'error';
  intent: Intent;
  generated_sql: string | null;
  previous_sql: string | null;
  is_valid: boolean;
  error_msg: string | null;
  retry_count: number;
  explanation: string;
  original_error: string | null;
  optimization_tips: string[];
  query_results: QueryResults | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sql?: string;
  response?: ChatResponse;
}

export interface DatabaseSchema {
  ddl: string;
  tables: Record<
    string,
    {
      name: string;
      columns: Record<string, string>;
      primary_keys: string[];
      foreign_keys: { column: string; referenced_table: string; referenced_column: string }[];
    }
  >;
}
