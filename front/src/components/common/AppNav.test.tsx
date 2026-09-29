import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppNav } from './AppNav';

function renderNav(initialPath: string) {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppNav />
    </MemoryRouter>
  );
}

describe('AppNav', () => {
  it('links to the new-plan and plans-list routes', () => {
    renderNav('/');

    expect(screen.getByRole('link', { name: 'Новый план' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Сгенерированные планы' })).toHaveAttribute('href', '/plans');
  });

  it('marks only the current route active', () => {
    renderNav('/plans');

    expect(screen.getByRole('link', { name: 'Сгенерированные планы' })).toHaveClass('app-nav__link--active');
    expect(screen.getByRole('link', { name: 'Новый план' })).not.toHaveClass('app-nav__link--active');
  });
});
