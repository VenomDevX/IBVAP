import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import DataTable, { type Column } from '../src/components/ui/DataTable';

interface Row { id: string; name: string; score: number }

const rows: Row[] = [
  { id: 'a', name: 'Charlie', score: 10 },
  { id: 'b', name: 'Alpha', score: 30 },
  { id: 'c', name: 'Bravo', score: 20 },
];

const columns: Column<Row>[] = [
  { key: 'name', header: 'Name', sortable: true },
  { key: 'score', header: 'Score', sortable: true, align: 'right' },
];

const bodyNames = () => within(screen.getAllByRole('rowgroup')[1]).getAllByRole('row').map(row => (row as HTMLTableRowElement).cells[0].textContent);

describe('DataTable', () => {
  it('sorts client-side and exposes aria-sort on the header', () => {
    render(<DataTable label="People" columns={columns} rows={rows} rowKey={r => r.id} />);
    const header = screen.getByRole('button', { name: 'Name' }).closest('th')!;
    expect(header).toHaveAttribute('aria-sort', 'none');

    fireEvent.click(screen.getByRole('button', { name: 'Name' }));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(bodyNames()).toEqual(['Alpha', 'Bravo', 'Charlie']);

    fireEvent.click(screen.getByRole('button', { name: 'Name' }));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    expect(bodyNames()).toEqual(['Charlie', 'Bravo', 'Alpha']);
  });

  it('in server mode reports sort changes and keeps row order as given', () => {
    const onSortChange = vi.fn();
    render(
      <DataTable label="People" columns={columns} rows={rows} rowKey={r => r.id}
        sort={{ key: 'score', dir: 'asc' }} onSortChange={onSortChange} pageSize={2} />,
    );
    expect(bodyNames()).toEqual(['Charlie', 'Alpha', 'Bravo']);
    expect(screen.queryByRole('button', { name: /next/i })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Score' }));
    expect(onSortChange).toHaveBeenCalledWith({ key: 'score', dir: 'desc' });
  });

  it('filters with the search prop and shows the empty title', () => {
    render(<DataTable label="People" columns={columns} rows={rows} rowKey={r => r.id} search="zulu" emptyTitle="No people found" />);
    expect(screen.getByText('No people found')).toBeInTheDocument();
  });
});
