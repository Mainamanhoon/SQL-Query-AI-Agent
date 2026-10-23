import { ArrowDown, ArrowUp, ArrowUpRight, Bot, MessageSquareText, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { ChatMessage, ChatResponse } from '../types/chat';

const examples = [
  { title: 'Explore customers', text: 'Show all customers and their states' },
  { title: 'Connect the dots', text: 'Show orders with customer names' },
  { title: 'Find a product', text: 'List products priced below 60 dollars' },
];

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  onSend: (text: string) => Promise<void>;
  onSelect: (response: ChatResponse) => void;
}

export function ChatWindow({ messages, loading, error, onSend, onSelect }: Props) {
  const [draft, setDraft] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const lastSubmitted = useRef('');

  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading, error]);
  useEffect(() => {
    if (error) setDraft(lastSubmitted.current);
  }, [error]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!draft.trim() || loading) return;
    lastSubmitted.current = draft;
    void onSend(draft);
    setDraft('');
  }

  return (
    <section className="chat-pane" aria-label="Conversation">
      <div className="pane-heading">
        <span>
          <MessageSquareText size={16} /> Conversation
        </span>
        <span className="subtle-label">SESSION / 01</span>
      </div>
      <div className="chat-scroll" aria-live="polite" aria-busy={loading}>
        {messages.length === 0 ? (
          <div className="welcome">
            <div className="welcome-symbol">
              <Sparkles size={25} strokeWidth={1.5} />
            </div>
            <div className="eyebrow">LESS SQL. MORE ANSWERS.</div>
            <h2>
              Your data has a story.
              <br />
              Start with a question.
            </h2>
            <p>
              Explore customers, products, and orders in plain English. I’ll take care of the query.
            </p>
            <div className="suggestions">
              {examples.map((example) => (
                <button
                  key={example.title}
                  className="suggestion"
                  onClick={() => setDraft(example.text)}
                >
                  <span>
                    <strong>{example.title}</strong>
                    <small>{example.text}</small>
                  </span>
                  <ArrowUpRight size={17} />
                </button>
              ))}
            </div>
            <div className="welcome-note">
              <ArrowDown size={13} /> Or ask your own question below
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <article key={message.id} className={`message message-${message.role}`}>
              <div className="message-label">
                {message.role === 'user' ? <span className="user-dot">Y</span> : <Bot size={16} />}
                <strong>{message.role === 'user' ? 'You' : 'QueryDesk'}</strong>
              </div>
              <p>{message.content}</p>
              {message.response?.status === 'success' && (
                <button className="text-button" onClick={() => onSelect(message.response!)}>
                  View query & results <ArrowUpRight size={13} />
                </button>
              )}
              {message.response?.status === 'clarification' && (
                <span className="message-tag">A little more detail needed</span>
              )}
            </article>
          ))
        )}
        {loading && (
          <div className="thinking">
            <span className="pulse-dot" /> Working through your question
            <span className="thinking-dots">…</span>
          </div>
        )}
        {error && (
          <div className="error-notice" role="alert">
            {error}
          </div>
        )}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={submit}>
        <label htmlFor="question" className="sr-only">
          Ask about your data
        </label>
        <textarea
          id="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask about your data…"
          rows={3}
          maxLength={4000}
          disabled={loading}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-bottom">
          <span>Shift + Enter for a new line</span>
          <button
            className="send-button"
            type="submit"
            disabled={loading || !draft.trim()}
            aria-label="Send message"
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </form>
      <div className="chat-footnote">Read-only by design. Your data stays unchanged.</div>
    </section>
  );
}
