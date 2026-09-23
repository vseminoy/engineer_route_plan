interface Props {
  message: string;
  onDismiss: () => void;
}

// 04_tor_frontend.md §6 — backend errors surface as a plain-language
// message, never a stack trace, and never block the whole screen
// (OSRM_UNAVAILABLE is the one exception, handled by the caller as a
// full-screen notice instead of this toast).
export function ErrorToast({ message, onDismiss }: Props) {
  return (
    <div className="error-toast" role="alert">
      <span>{message}</span>
      <button
        aria-label="Закрыть уведомление"
        onClick={onDismiss}
        style={{ marginLeft: 12, background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}
      >
        ×
      </button>
    </div>
  );
}
