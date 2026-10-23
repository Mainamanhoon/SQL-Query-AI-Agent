import { Download, Rows3, Table2 } from 'lucide-react';
import { downloadResults } from '../services/csv';
import type { QueryResults } from '../types/chat';

export function ResultsTable({ results }: { results: QueryResults | null }) {
  return (
    <section className="workspace-card results-card" aria-label="Query results">
      <div className="card-heading">
        <span>
          <Table2 size={16} /> Results{' '}
          {results && <span className="result-count">{results.rows.length} rows</span>}
        </span>
        <button
          className="small-button"
          disabled={!results}
          onClick={() => results && downloadResults(results)}
        >
          <Download size={13} /> Export CSV
        </button>
      </div>
      {results ? (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th className="row-index">#</th>
                  {results.columns.map((column, index) => (
                    <th key={`${column}-${index}`}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.rows.map((row, index) => (
                  <tr key={index}>
                    <td className="row-index">{index + 1}</td>
                    {row.map((cell, column) => (
                      <td key={column}>
                        {cell === null ? <span className="null-value">NULL</span> : String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {results.rows.length === 0 && (
            <div className="no-matches">No matching records. Try broadening your filters.</div>
          )}
          <div className="results-footer">
            <span>
              {results.truncated
                ? `Showing the first ${results.row_limit} rows · result truncated`
                : `${results.rows.length} records returned`}
            </span>
            <span>{results.elapsed_ms.toFixed(1)} ms</span>
          </div>
        </>
      ) : (
        <div className="empty-results">
          <div className="table-illustration">
            <Rows3 size={35} strokeWidth={1} />
            <span className="table-spark">✦</span>
          </div>
          <h3>A little curiosity goes a long way.</h3>
          <p>
            Ask a question to see your data here.
            <br />
            Results appear automatically after validation.
          </p>
        </div>
      )}
    </section>
  );
}
