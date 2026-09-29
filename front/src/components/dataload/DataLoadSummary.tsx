import { invalidRowReasonText } from '@/lib/labels';
import type { DataLoadResult } from '@/types/domain';

interface Props {
  result: DataLoadResult;
  onBuild: () => void;
  onDismiss: () => void;
}

// Shown instead of an automatic redirect when the load skipped invalid rows —
// the dispatcher decides whether to build the plan as-is or fix the file and
// upload again.
export function DataLoadSummary({ result, onBuild, onDismiss }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 14 }}>
        Бригад: {result.engineersCount} · Заявок загружено: {result.ticketsCount} · Пропущено строк:{' '}
        {result.rowsSkipped} из {result.rowsTotal}
      </div>
      <div style={{ fontSize: 13, color: 'var(--color-danger-text)', fontWeight: 600 }}>
        Не загружено строк: {result.invalidRows.length}
      </div>
      <ul
        style={{
          margin: 0,
          padding: 0,
          listStyle: 'none',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          maxHeight: 240,
          overflowY: 'auto'
        }}
      >
        {result.invalidRows.map((row) => (
          <li key={row.row} style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Строка {row.row}
            {row.column ? `, колонка «${row.column}»` : ''}: {invalidRowReasonText[row.reason]}
          </li>
        ))}
      </ul>
      <div style={{ display: 'flex', gap: 12 }}>
        <button className="btn-primary" onClick={onBuild}>
          Построить план
        </button>
        <button onClick={onDismiss}>Загрузить другой файл</button>
      </div>
    </div>
  );
}
