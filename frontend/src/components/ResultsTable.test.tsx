import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ResultsTable } from './ResultsTable';

it('distinguishes an empty query result from the initial empty workspace', () => {
  render(
    <ResultsTable
      results={{ columns: ['name'], rows: [], truncated: false, elapsed_ms: 1, row_limit: 200 }}
    />,
  );
  expect(screen.getByText(/No matching records/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Export CSV' })).toBeEnabled();
});

it('renders cells as text and makes truncation visible', () => {
  render(
    <ResultsTable
      results={{
        columns: ['name'],
        rows: [['<script>alert(1)</script>']],
        truncated: true,
        elapsed_ms: 2,
        row_limit: 1,
      }}
    />,
  );
  expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument();
  expect(screen.getByText(/result truncated/)).toBeInTheDocument();
  expect(document.querySelector('script')).toBeNull();
});
