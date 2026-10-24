import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SQLPanel } from './SQLPanel';

describe('SQLPanel', () => {
  it('restores the generated query when an empty edit is closed', () => {
    render(
      <SQLPanel
        query="SELECT name FROM Users"
        retries={0}
        running={false}
        onRun={vi.fn(async () => undefined)}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /edit sql/i }));
    const editor = screen.getByRole('textbox', { name: 'SQL editor' });
    fireEvent.change(editor, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /restore sql/i }));

    expect(screen.queryByRole('textbox', { name: 'SQL editor' })).toBeNull();
    expect(document.querySelector('code')?.textContent).toContain('SELECT name FROM Users');
  });
});
