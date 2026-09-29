import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TicketStatusControl } from './TicketStatusControl';

describe('TicketStatusControl', () => {
  it('offers only the statuses reachable from the current one, current excluded', () => {
    render(<TicketStatusControl status="en_route" pending={false} onChange={vi.fn()} />);

    const options = screen.getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['Изменить статус…', 'Работа начата', 'Завершена', 'Отменена', 'Просрочена']);
  });

  it('calls onChange with the selected status when saved', () => {
    const onChange = vi.fn();
    render(<TicketStatusControl status="sent" pending={false} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText('Новый статус заявки'), { target: { value: 'en_route' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

    expect(onChange).toHaveBeenCalledWith('en_route');
  });

  it('shows no control for a closed status', () => {
    render(<TicketStatusControl status="completed" pending={false} onChange={vi.fn()} />);

    expect(screen.getByText('Статус закрыт, изменить нельзя.')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('shows the error message passed by the parent', () => {
    render(<TicketStatusControl status="sent" pending={false} error="Недопустимый переход" onChange={vi.fn()} />);

    expect(screen.getByText('Недопустимый переход')).toBeInTheDocument();
  });

  it('disables the save button while a change is pending', () => {
    render(<TicketStatusControl status="sent" pending={true} onChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Сохраняем…' })).toBeDisabled();
  });
});
