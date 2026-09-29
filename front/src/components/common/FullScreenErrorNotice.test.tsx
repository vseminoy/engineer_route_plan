import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FullScreenErrorNotice } from './FullScreenErrorNotice';

describe('FullScreenErrorNotice', () => {
  it('shows the message and calls onRetry when the button is clicked', () => {
    const onRetry = vi.fn();
    render(
      <FullScreenErrorNotice
        message="Сервис временно недоступен, попробуйте ещё раз"
        retryLabel="Повторить"
        onRetry={onRetry}
      />
    );

    expect(screen.getByText('Сервис временно недоступен, попробуйте ещё раз')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('disables the button and swaps its label while retrying', () => {
    render(<FullScreenErrorNotice message="Не удалось построить план" retryLabel="Построить заново" retrying onRetry={vi.fn()} />);

    const button = screen.getByRole('button', { name: 'Строим…' });
    expect(button).toBeDisabled();
  });
});
