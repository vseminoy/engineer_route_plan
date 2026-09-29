import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileUploadForm } from './FileUploadForm';

// FileUploadForm reports validation through `onFileSelected`; this wrapper feeds
// that back into `error` the way DataLoadScreen's field-error map does, so the
// test exercises the field showing its own error rather than a spy's arguments.
function Wrapper({ onSubmit }: { onSubmit: (file: File) => void }) {
  const [error, setError] = useState<string | undefined>();
  return (
    <FileUploadForm
      disabled={false}
      error={error}
      onFileSelected={(_file, message) => setError(message ?? undefined)}
      onSubmit={onSubmit}
    />
  );
}

function selectFile(container: HTMLElement, file: File) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

describe('FileUploadForm', () => {
  it('rejects an unsupported extension under the field, before submit', () => {
    const { container } = render(<Wrapper onSubmit={vi.fn()} />);
    selectFile(container, new File(['x'], 'tickets.txt'));

    expect(screen.getByText('Поддерживаются только файлы .csv или .json.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Загрузить и построить план' })).toBeDisabled();
  });

  it('rejects an empty file under the field', () => {
    const { container } = render(<Wrapper onSubmit={vi.fn()} />);
    selectFile(container, new File([], 'tickets.csv'));

    expect(screen.getByText('Файл пустой.')).toBeInTheDocument();
  });

  it('accepts a valid file, enables submit, and passes the file through', () => {
    const onSubmit = vi.fn();
    const { container } = render(<Wrapper onSubmit={onSubmit} />);
    const validFile = new File(['a;b\n1;2'], 'tickets.csv', { type: 'text/csv' });
    selectFile(container, validFile);

    const button = screen.getByRole('button', { name: 'Загрузить и построить план' });
    expect(button).toBeEnabled();
    fireEvent.click(button);

    expect(onSubmit).toHaveBeenCalledWith(validFile);
  });
});
