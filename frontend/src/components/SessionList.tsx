import { Clock3, MessageCircle } from 'lucide-react';
import type { ChatSession } from '../types/chat';

interface Props {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelect: (sessionId: string) => void;
}

export function SessionList({ sessions, activeSessionId, onSelect }: Props) {
  return (
    <section className="session-history" aria-label="Conversation history">
      <div className="session-heading">
        <span className="sidebar-label">CONVERSATIONS</span>
        <Clock3 size={13} />
      </div>
      <div className="session-list">
        {sessions.map((session) => (
          <button
            key={session.id}
            type="button"
            className={`session-item ${session.id === activeSessionId ? 'session-item-active' : ''}`}
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
        ))}
      </div>
    </section>
  );
}
