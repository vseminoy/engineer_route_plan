interface Props {
  disabled: boolean;
  onClick: () => void;
}

export function DemoDatasetButton({ disabled, onClick }: Props) {
  return (
    <button className="btn-primary" disabled={disabled} onClick={onClick} style={{ background: 'var(--color-text-primary)' }}>
      Использовать демо-набор
    </button>
  );
}
