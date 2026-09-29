import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RegionSelect } from './RegionSelect';

// useRegions hits the network through the generated client; stubbed here so the
// component falls back to its built-in region list, same as an empty response.
vi.mock('@/queries/useRegions', () => ({
  useRegions: () => ({ data: undefined })
}));

describe('RegionSelect', () => {
  it('shows the field error passed by the parent', () => {
    render(<RegionSelect value={null} onChange={vi.fn()} error="Некорректный регион" />);

    expect(screen.getByText('Некорректный регион')).toBeInTheDocument();
  });

  it('fires onBlur so the parent can (re)validate the region field', () => {
    const onBlur = vi.fn();
    render(<RegionSelect value="east" onChange={vi.fn()} onBlur={onBlur} />);

    fireEvent.blur(screen.getByRole('combobox'));

    expect(onBlur).toHaveBeenCalledTimes(1);
  });
});
