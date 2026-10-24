import { Check, CheckCheck, Code2, Copy, LoaderCircle, Pencil, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

SyntaxHighlighter.registerLanguage('sql', sql);

interface Props {
  query: string | null;
  retries: number;
  running: boolean;
  onRun: (sql: string) => Promise<void>;
}

export function SQLPanel({ query, retries, running, onRun }: Props) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [editedQuery, setEditedQuery] = useState(query || '');
  const [editing, setEditing] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  useEffect(() => {
    setCopyStatus('idle');
    setEditedQuery(query || '');
    setEditing(false);
    setRunError(null);
  }, [query]);
  useEffect(() => {
    if (copyStatus === 'idle') return;
    const timeout = setTimeout(() => setCopyStatus('idle'), 2500);
    return () => clearTimeout(timeout);
  }, [copyStatus]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(editedQuery);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  }

  async function run() {
    setRunError(null);
    try {
      await onRun(editedQuery);
      setEditing(false);
    } catch (failure) {
      setRunError(failure instanceof Error ? failure.message : 'SQL execution failed.');
    }
  }

  return (
    <section className="workspace-card sql-card" aria-label="Generated SQL">
      <div className="card-heading">
        <span>
          <Code2 size={17} /> SQL query <span className="language-tag">SQLite</span>
        </span>
        <div className="card-actions">
          <button
            className="small-button"
            type="button"
            onClick={() => {
              setEditing((value) => !value);
              setRunError(null);
            }}
            disabled={!query || running}
          >
            <Pencil size={13} /> {editing ? 'Done' : 'Edit SQL'}
          </button>
          <button
            className="run-button"
            type="button"
            onClick={() => void run()}
            disabled={!editedQuery.trim() || running}
          >
            {running ? <LoaderCircle className="spin" size={13} /> : <Play size={13} />}
            {running ? 'Running' : 'Run SQL'}
          </button>
          <button className="small-button" type="button" onClick={() => void copy()} disabled={!query}>
            {copyStatus === 'copied' ? <Check size={13} /> : <Copy size={13} />}
            {copyStatus === 'copied'
              ? 'Copied'
              : copyStatus === 'failed'
                ? 'Copy failed'
                : 'Copy SQL'}
          </button>
        </div>
      </div>
      {query ? (
        editing ? (
          <textarea
            className="sql-editor"
            aria-label="SQL editor"
            value={editedQuery}
            onChange={(event) => {
              setEditedQuery(event.target.value);
              setRunError(null);
            }}
            spellCheck={false}
          />
        ) : (
          <SyntaxHighlighter
            language="sql"
            style={oneLight}
            showLineNumbers
            wrapLongLines
            customStyle={{
              margin: 0,
              background: 'transparent',
              padding: '24px 20px',
              fontSize: 13,
              lineHeight: 1.9,
            }}
            lineNumberStyle={{ color: '#b3b9b1', minWidth: '2.5em' }}
          >
            {editedQuery}
          </SyntaxHighlighter>
        )
      ) : (
        <div className="empty-code">
          <span className="line-number">1</span>
          <span>-- Your next insight starts with a question.</span>
          <br />
          <span className="line-number">2</span>
          <span>-- Generated SQL will appear here.</span>
          <br />
          <span className="line-number">3</span>
          <span className="code-cursor" />
        </div>
      )}
      {runError && (
        <div className="sql-run-error" role="alert">
          {runError}
        </div>
      )}
      <div className="sql-footer">
        <span>
          <CheckCheck size={14} />{' '}
          {query ? 'Validated against your schema' : 'Queries are validated before execution'}
        </span>
        {retries > 0 && (
          <span>
            {retries} repair{retries > 1 ? 's' : ''}
          </span>
        )}
      </div>
    </section>
  );
}
