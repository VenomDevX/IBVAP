import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DataTable, { type Column } from '../src/components/ui/DataTable';

type Row = { id: string; score: number };

describe('DataTable', () => {
  it('exposes accessible sort state and sorts from a keyboard-operable button', () => {
    const columns: Column<Row>[] = [
      { key: 'id', header: 'Incident' },
      { key: 'score', header: 'Score', sortable: true },
    ];
    render(<DataTable columns={columns} rows={[{ id: 'low', score: 1 }, { id: 'high', score: 9 }]} rowKey={row => row.id} />);

    const scoreHeader = screen.getByRole('columnheader', { name: 'Score' });
    expect(scoreHeader).toHaveAttribute('aria-sort', 'none');
    fireEvent.click(within(scoreHeader).getByRole('button'));
    expect(scoreHeader).toHaveAttribute('aria-sort', 'ascending');
    expect(within(screen.getAllByRole('row')[1]).getByText('low')).toBeInTheDocument();
  });
});
