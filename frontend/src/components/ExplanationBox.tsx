import { Lightbulb, Wrench } from 'lucide-react';
import type { ChatResponse } from '../types/chat';

export function ExplanationBox({ response }: { response: ChatResponse | null }) {
  return (
    <section className="explanation-box" aria-label="Query explanation">
      <div className="explanation-icon">
        <Lightbulb size={17} />
      </div>
      <div>
        <h3>
          {response?.status === 'clarification'
            ? 'Let’s clarify'
            : response?.status === 'rejected'
              ? 'A quick note'
              : 'What this query does'}
        </h3>
        <p>
          {response?.explanation ||
            'A plain-English explanation of your query, including the tables, filters, and relationships behind the answer.'}
        </p>
        {response?.original_error && (
          <div className="debug-detail">
            <strong>
              <Wrench size={13} /> What was fixed
            </strong>
            <p>{response.original_error}</p>
          </div>
        )}
        {!!response?.optimization_tips.length && (
          <div className="optimization-tips">
            <strong>Performance notes</strong>
            <ul>
              {response.optimization_tips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
