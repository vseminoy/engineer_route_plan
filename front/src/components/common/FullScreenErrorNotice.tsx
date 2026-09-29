interface Props {
  message: string;
  retryLabel: string;
  onRetry: () => void;
  retrying?: boolean;
}

// A full-screen counterpart to ErrorToast/LoadingOverlay for failures that
// block the whole screen rather than one request: a plan build that never
// got queued (503/500) or one that queued and then failed — both need the
// dispatcher to explicitly retry rather than silently reload.
export function FullScreenErrorNotice({ message, retryLabel, onRetry, retrying }: Props) {
  return (
    <div className="loading-overlay">
      <div>{message}</div>
      <button className="btn-primary" onClick={onRetry} disabled={retrying}>
        {retrying ? 'Строим…' : retryLabel}
      </button>
    </div>
  );
}
