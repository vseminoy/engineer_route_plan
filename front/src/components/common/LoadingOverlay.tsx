interface Props {
  text: string;
}

// A skeleton/loader shown while a backend request is in flight, so a slow
// response doesn't read as a frozen screen.
export function LoadingOverlay({ text }: Props) {
  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div>{text}</div>
    </div>
  );
}
