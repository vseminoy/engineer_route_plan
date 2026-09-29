interface Props {
  message: string;
  onDismiss: () => void;
}

// Backend errors surface as a plain-language message (built by the caller via
// describeError), never a stack trace, and never block the whole screen — a
// 503 on plan build/replan is the one exception, shown by the caller as a
// full-screen notice instead of this toast.
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
