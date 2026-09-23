interface Props {
  text: string;
}

// 04_tor_frontend.md §7 — perceived-latency budget is covered by this
// skeleton/loader while the backend request is in flight.
export function LoadingOverlay({ text }: Props) {
  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div>{text}</div>
    </div>
  );
}
