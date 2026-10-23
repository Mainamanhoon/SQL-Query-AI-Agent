import type { QueryResults } from '../types/chat';

export function resultsToCsv(results: QueryResults): string {
  function escape(value: string | number | null): string {
    const text = value === null ? '' : String(value);
    // Prevent spreadsheet formula execution when exporting untrusted text cells.
    const safe = typeof value === 'string' && /^[\s]*[=+@-]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  }
  return [results.columns, ...results.rows].map((row) => row.map(escape).join(',')).join('\r\n');
}

export function downloadResults(results: QueryResults): void {
  const url = URL.createObjectURL(
    new Blob(['\uFEFF', resultsToCsv(results)], { type: 'text/csv;charset=utf-8' }),
  );
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'query-results.csv';
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
