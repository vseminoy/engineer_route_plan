import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EngineerSetSelect } from './EngineerSetSelect';
import type { EngineerSet } from '@/types/domain';

const demoSet: EngineerSet = {
  id: 1,
  name: 'default',
  kind: 'demo',
  engineers: 10,
  morningShare: 0.5,
  eveningShare: 0.5,
  seed: 'demo',
  description: '10 бригад, 50%/50%, seed demo'
};

const generatedSet: EngineerSet = {
  id: 7,
  name: '13 бригад',
  kind: 'generated',
  engineers: 13,
  morningShare: 0.6,
  eveningShare: 0.4,
  seed: 'demo-13',
  description: '13 бригад, 60%/40%, seed demo-13'
};

let sets: EngineerSet[] = [demoSet];
vi.mock('@/queries/useEngineerSets', () => ({
  useEngineerSets: () => ({ data: sets })
}));

describe('EngineerSetSelect', () => {
  it('offers only the default option and no delete button when the region has no extra sets', () => {
    sets = [demoSet];
    render(
      <EngineerSetSelect region="east" value={null} onChange={vi.fn()} onCreateClick={vi.fn()} onDeleteClick={vi.fn()} />
    );

    expect(screen.getByRole('option', { name: 'По умолчанию' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Удалить набор' })).not.toBeInTheDocument();
  });

  it('reports the chosen set id, and null back for the default set', () => {
    sets = [demoSet, generatedSet];
    const onChange = vi.fn();
    render(
      <EngineerSetSelect region="east" value={null} onChange={onChange} onCreateClick={vi.fn()} onDeleteClick={vi.fn()} />
    );

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '7' } });
    expect(onChange).toHaveBeenCalledWith(7);

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('shows a delete button for the selected generated set and reports it on click', () => {
    sets = [demoSet, generatedSet];
    const onDeleteClick = vi.fn();
    render(
      <EngineerSetSelect region="east" value={7} onChange={vi.fn()} onCreateClick={vi.fn()} onDeleteClick={onDeleteClick} />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Удалить набор' }));

    expect(onDeleteClick).toHaveBeenCalledWith(generatedSet);
  });
});
