import { useRef, useState } from 'react';

interface Props {
  disabled: boolean;
  onSubmit: (ticketsFile: File, engineersFile?: File) => void;
}

function hasValidExtension(file: File): boolean {
  return /\.(csv|json)$/i.test(file.name);
}

// 06_spec_frontend.md §3.1 — client-side validation is limited to
// extension + non-empty file; everything else is a backend VALIDATION_ERROR
// shown inline under the field, never a technical stack trace.
export function FileUploadForm({ disabled, onSubmit }: Props) {
  const [ticketsFile, setTicketsFile] = useState<File | null>(null);
  const [engineersFile, setEngineersFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function acceptTicketsFile(file: File) {
    if (!hasValidExtension(file)) {
      setError('Поддерживаются только файлы .csv или .json.');
      return;
    }
    if (file.size === 0) {
      setError('Файл пустой.');
      return;
    }
    setError(null);
    setTicketsFile(file);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) acceptTicketsFile(file);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDragOver ? 'var(--color-accent)' : 'rgba(18,21,26,0.2)'}`,
          borderRadius: 12,
          padding: 24,
          textAlign: 'center',
          cursor: 'pointer',
          fontSize: 14,
          color: 'var(--color-text-secondary)'
        }}
      >
        {ticketsFile ? ticketsFile.name : 'Перетащите файл заявок сюда или нажмите, чтобы выбрать (.csv, .json)'}
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.json"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) acceptTicketsFile(file);
          }}
        />
      </div>
      {error && <div style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{error}</div>}

      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--color-text-secondary)' }}>
        Файл бригад (опционально)
        <input
          type="file"
          accept=".csv,.json"
          onChange={(e) => setEngineersFile(e.target.files?.[0] ?? null)}
        />
      </label>

      <button
        className="btn-primary"
        disabled={disabled || !ticketsFile}
        onClick={() => ticketsFile && onSubmit(ticketsFile, engineersFile ?? undefined)}
      >
        Загрузить и построить план
      </button>
    </div>
  );
}
