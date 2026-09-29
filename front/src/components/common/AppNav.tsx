import { NavLink } from 'react-router-dom';

// Present on every screen (DataLoadScreen, PlanScreen, PlansScreen) so a
// dispatcher can jump between "start a new plan" and "browse built plans"
// without going back to a specific plan's URL first.
export function AppNav() {
  return (
    <nav className="app-nav" aria-label="Разделы">
      <NavLink to="/" end className={({ isActive }) => `app-nav__link${isActive ? ' app-nav__link--active' : ''}`}>
        Новый план
      </NavLink>
      <NavLink
        to="/plans"
        className={({ isActive }) => `app-nav__link${isActive ? ' app-nav__link--active' : ''}`}
      >
        Сгенерированные планы
      </NavLink>
    </nav>
  );
}
