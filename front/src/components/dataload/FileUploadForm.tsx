import { useRef, useState } from 'react';
import { validateTicketsFile } from '@/lib/fileValidation';

interface Props {
  disabled: boolean;
  error?: string;
  onFileSelected: (file: File | null, error: string | null) => void;
  onSubmit: (ticketsFile: File) => void;
}

// Client-side validation is extension + non-empty + size limit
// (validateTicketsFile); the file's content is a backend concern, shown
// inline under the field (`error`, from the parent's field-error map).
export function FileUploadForm({ disabled, error, onFileSelected, onSubmit }: Props) {
  const [ticketsFile, setTicketsFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function acceptFile(file: File) {
    const message = validateTicketsFile(file);
    setTicketsFile(message ? null : file);
    onFileSelected(message ? null : file, message);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) acceptFile(file);
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
            if (file) acceptFile(file);
          }}
        />
      </div>
      {error && <div style={{ fontSize: 13, color: 'var(--color-danger-text)' }}>{error}</div>}

      <button
        className="btn-primary"
        disabled={disabled || !ticketsFile}
        onClick={() => ticketsFile && onSubmit(ticketsFile)}
      >
        Загрузить и построить план
      </button>
    </div>
  );
}
