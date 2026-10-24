import {
  ChevronDown,
  CircleHelp,
  Database,
  KeyRound,
  Layers3,
  Menu,
  MessageSquareCode,
  Moon,
  Plus,
  ShieldCheck,
  Sun,
  Table2,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { ChatWindow } from './components/ChatWindow';
import { ExplanationBox } from './components/ExplanationBox';
import { ResultsTable } from './components/ResultsTable';
import { SessionList } from './components/SessionList';
import { SQLPanel } from './components/SQLPanel';
import { useChat } from './hooks/useChat';
import { getHealth, getSchema } from './services/api';
import type { DatabaseSchema } from './types/chat';

export default function App() {
  const chat = useChat();
  const [schema, setSchema] = useState<DatabaseSchema | null>(null);
  const [connection, setConnection] = useState<'connecting' | 'ready' | 'setup' | 'offline'>(
    'connecting',
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === 'undefined') return false;
    const stored = localStorage.getItem('querydesk.theme');
    return stored ? stored === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [conversationVersion, setConversationVersion] = useState(0);

  useEffect(() => {
    localStorage.setItem('querydesk.theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  useEffect(() => {
    let active = true;
    Promise.all([getSchema(), getHealth()])
      .then(([schemaResult, health]) => {
        if (active) {
          setSchema(schemaResult);
          setConnection(health.model_configured ? 'ready' : 'setup');
        }
      })
      .catch(() => {
        if (active) setConnection('offline');
      });
    return () => {
      active = false;
    };
  }, []);

  const response = chat.selectedResponse;
  const connectionLabel = {
    connecting: 'Connecting',
    ready: 'Connected',
    setup: 'Model setup needed',
    offline: 'API unavailable',
  }[connection];

  return (
    <div className={`app-shell ${darkMode ? 'theme-dark' : ''}`}>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <a className="brand" href="/" aria-label="QueryDesk home">
          <span className="brand-mark">
            <MessageSquareCode size={23} />
          </span>
          QueryDesk<span className="brand-period">.</span>
        </a>
        <div className="sidebar-workspace">
          <span className="workspace-avatar">E</span>
          <div>
            <strong>Ecommerce</strong>
            <small>Sample workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <button
          className="new-chat"
          onClick={() => {
            chat.newSession();
            setConversationVersion((value) => value + 1);
            setSidebarOpen(false);
          }}
        >
          <Plus size={16} /> New conversation <span>↗</span>
        </button>
        <div className="sidebar-label">WORKSPACE</div>
        <div className="sidebar-active">
          <MessageSquareCode size={17} /> SQL assistant <span className="active-dot" />
        </div>
        <SessionList
          sessions={chat.sessions}
          activeSessionId={chat.activeSessionId}
          onSelect={(sessionId) => {
            chat.selectSession(sessionId);
            setSidebarOpen(false);
          }}
          onDelete={chat.deleteSession}
        />
        <div className="schema-heading">
          <span className="sidebar-label">DATABASE SCHEMA</span>
          <span>{schema ? Object.keys(schema.tables).length : '—'} tables</span>
        </div>
        <nav className="schema-list" aria-label="Database schema">
          {schema ? (
            Object.values(schema.tables).map((table) => (
              <details key={table.name} className="schema-table">
                <summary>
                  <Table2 size={14} />
                  <span>{table.name}</span>
                  <ChevronDown size={12} />
                </summary>
                <div className="schema-columns">
                  {Object.entries(table.columns).map(([column, type]) => {
                    const relation = table.foreign_keys.find(
                      (foreignKey) => foreignKey.column === column,
                    );
                    return (
                      <div
                        key={column}
                        title={
                          relation
                            ? `References ${relation.referenced_table}.${relation.referenced_column}`
                            : type
                        }
                      >
                        <span>
                          {table.primary_keys.includes(column) ? (
                            <KeyRound size={10} />
                          ) : (
                            <span className="column-dot" />
                          )}
                          {column}
                        </span>
                        <small>{relation ? 'FK' : type.toLowerCase()}</small>
                      </div>
                    );
                  })}
                </div>
              </details>
            ))
          ) : (
            <p className="schema-placeholder">
              {connection === 'offline' ? 'Start the API to load your schema.' : 'Loading schema…'}
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="safety-card">
            <ShieldCheck size={18} />
            <strong>Safe to explore</strong>
            <p>
              Every query is checked.
              <br />
              Your database is read-only.
            </p>
          </div>
          <button className="help-button" onClick={() => setHelpOpen(!helpOpen)}>
            <CircleHelp size={16} /> How it works
          </button>
          <div className="sidebar-signoff">A clearer view of your data.</div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={20} />
            </button>
            <Layers3 size={15} />
            <span>Workspace</span>
            <span className="breadcrumb-divider">/</span>
            <strong>SQL assistant</strong>
          </div>
          <div className="connection-pill">
            <span className={`connection-dot ${connection === 'ready' ? 'is-ready' : ''}`} />
            <span>{connectionLabel}</span>
            <span className="connection-divider" />
            <Database size={12} />
            <span>SQLite</span>
          </div>
          <button
            className="theme-toggle"
            type="button"
            aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-pressed={darkMode}
            onClick={() => setDarkMode((value) => !value)}
          >
            {darkMode ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </header>
        <div className="page-heading">
          <div>
            <div className="eyebrow">YOUR DATA, IN PLAIN ENGLISH</div>
            <h1>Ask. Explore. Understand.</h1>
            <p>Turn a question into a query — and a query into clarity.</p>
          </div>
          <div className="database-label">
            <Database size={15} />
            <span>ecommerce.db</span>
            <span className="sample-badge">SAMPLE</span>
          </div>
        </div>
        {connection === 'offline' && (
          <div className="setup-banner" role="status">
            The API is unavailable. Check the backend connection, then reload this page.
          </div>
        )}
        {connection === 'setup' && (
          <div className="setup-banner" role="status">
            The database is ready. Configure the backend’s LLM_API_KEY and LLM_MODEL to enable the
            assistant.
          </div>
        )}
        {helpOpen && (
          <div className="help-panel">
            <button aria-label="Close help" onClick={() => setHelpOpen(false)}>
              <X size={16} />
            </button>
            <strong>One conversation, a few ways to explore.</strong>
            <p>
              Ask a question, paste SQL to debug or optimize it, or follow up with “Only
              California.” Expand a table in the sidebar to see its columns. The assistant only
              reads this sample database; unsupported requests receive a clear explanation.
            </p>
          </div>
        )}
        <div className="workbench">
          <ChatWindow
            key={conversationVersion}
            messages={chat.messages}
            loading={chat.loading}
            streamingText={chat.streamingText}
            error={chat.error}
            onSend={chat.send}
            onSelect={chat.setSelectedResponse}
          />
          <div className="output-pane">
            <div className="pane-heading">
              <span>
                <Layers3 size={16} /> Query workspace
              </span>
              <span className="subtle-label">SQL → INSIGHTS</span>
            </div>
            <div className="output-content">
              <SQLPanel
                query={response?.generated_sql || null}
                retries={response?.retry_count || 0}
                running={chat.sqlRunning}
                darkMode={darkMode}
                onRun={chat.runSql}
              />
              <ExplanationBox response={response} />
              <ResultsTable results={response?.query_results || null} />
            </div>
          </div>
        </div>
        <footer className="page-footer">
          <span>
            <ShieldCheck size={12} /> Read-only access · Schema-aware validation
          </span>
          <span>Built for questions worth asking.</span>
        </footer>
      </main>
    </div>
  );
}
