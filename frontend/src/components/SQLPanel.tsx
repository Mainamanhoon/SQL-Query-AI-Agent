import { Check, CheckCheck, Code2, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

SyntaxHighlighter.registerLanguage('sql', sql);

export function SQLPanel({ query, retries }: { query: string | null; retries: number }) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => {
    setCopyStatus('idle');
  }, [query]);
  useEffect(() => {
    if (copyStatus === 'idle') return;
    const timeout = setTimeout(() => setCopyStatus('idle'), 2500);
    return () => clearTimeout(timeout);
  }, [copyStatus]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(query || '');
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  }

  return (
    <section className="workspace-card sql-card" aria-label="Generated SQL">
      <div className="card-heading">
        <span>
          <Code2 size={17} /> SQL query <span className="language-tag">SQLite</span>
        </span>
        <button className="small-button" onClick={() => void copy()} disabled={!query}>
          {copyStatus === 'copied' ? <Check size={13} /> : <Copy size={13} />}
          {copyStatus === 'copied'
            ? 'Copied'
            : copyStatus === 'failed'
              ? 'Copy failed'
              : 'Copy SQL'}
        </button>
      </div>
      {query ? (
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
          {query}
        </SyntaxHighlighter>
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
