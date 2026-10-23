import { expect, it } from 'vitest';
import { resultsToCsv } from './csv';

it('escapes CSV text and protects spreadsheet formulas while preserving numeric values', () => {
  const csv = resultsToCsv({
    columns: ['name', 'amount'],
    rows: [
      ['a,"b', -5],
      ['=HYPERLINK("bad")', null],
    ],
    truncated: false,
    elapsed_ms: 1,
    row_limit: 200,
  });
  expect(csv).toContain('"a,""b","-5"');
  expect(csv).toContain('"\'=HYPERLINK(""bad"")",""');
});
