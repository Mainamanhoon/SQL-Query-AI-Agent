import { Clock3, MessageCircle, Trash2 } from 'lucide-react';
import type { ChatSession } from '../types/chat';

interface Props {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}

export function SessionList({ sessions, activeSessionId, onSelect, onDelete }: Props) {
  return (
    <section className="session-history" aria-label="Conversation history">
      <div className="session-heading">
        <span className="sidebar-label">CONVERSATIONS</span>
        <Clock3 size={13} />
      </div>
      <div className="session-list">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`session-item-row ${session.id === activeSessionId ? 'session-item-row-active' : ''}`}
          >
            <button
              type="button"
              className="session-item"
              onClick={() => onSelect(session.id)}
            >
              <MessageCircle size={14} />
              <span>
                <strong>{session.title}</strong>
                <small>
                  {session.messages.length
                    ? `${session.messages.length} message${session.messages.length === 1 ? '' : 's'}`
                    : 'Empty conversation'}
                </small>
              </span>
            </button>
            <button
              type="button"
              className="session-delete"
              aria-label={`Delete ${session.title}`}
              title="Delete conversation"
              onClick={() => onDelete(session.id)}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
