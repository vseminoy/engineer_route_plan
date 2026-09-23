import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RegionSelect } from './RegionSelect';
import { FileUploadForm } from './FileUploadForm';
import { DemoDatasetButton } from './DemoDatasetButton';
import { LoadingOverlay } from '@/components/common/LoadingOverlay';
import { ErrorToast } from '@/components/common/ErrorToast';
import { loadDemoDataset, uploadDataset } from '@/api/endpoints';
import { useBuildPlan } from '@/queries/useBuildPlan';
import { useUiStore } from '@/store/useUiStore';
import { describeApiError } from '@/lib/labels';
import { ApiError } from '@/api/client';

// Fixed demo day across all three regions' synthetic datasets
// (07_data_dictionary.md §1: "дата фиксирована — 17.08.2026").
const PLAN_DATE = '2026-08-17';

export function DataLoadScreen() {
  const navigate = useNavigate();
  const selectedRegion = useUiStore((s) => s.selectedRegion);
  const setSelectedRegion = useUiStore((s) => s.setSelectedRegion);
  const buildPlanMutation = useBuildPlan();
  const [loadingText, setLoadingText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runBuild() {
    if (!selectedRegion) return;
    setLoadingText('Строим план…');
    try {
      const { main } = await buildPlanMutation.mutateAsync({ region: selectedRegion, planDate: PLAN_DATE });
      navigate(`/plan/${main.planId}`);
    } catch (err) {
      setError(err instanceof ApiError ? describeApiError(err.errorCode, err.message) : 'Не удалось построить план.');
    } finally {
      setLoadingText(null);
    }
  }

  async function handleDemo() {
    if (!selectedRegion) return;
    setError(null);
    setLoadingText('Загружаем демо-набор…');
    try {
      await loadDemoDataset(selectedRegion);
      await runBuild();
    } catch (err) {
      setError(err instanceof ApiError ? describeApiError(err.errorCode, err.message) : 'Не удалось загрузить демо-набор.');
      setLoadingText(null);
    }
  }

  async function handleUpload(ticketsFile: File, engineersFile?: File) {
    if (!selectedRegion) return;
    setError(null);
    setLoadingText('Загружаем файл…');
    try {
      await uploadDataset(selectedRegion, ticketsFile, engineersFile);
      await runBuild();
    } catch (err) {
      setError(err instanceof ApiError ? describeApiError(err.errorCode, err.message) : 'Не удалось загрузить файл.');
      setLoadingText(null);
    }
  }

  return (
    <div style={{ maxWidth: 480, margin: '64px auto', padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Диспетчер маршрутов</h1>
      <RegionSelect value={selectedRegion} onChange={setSelectedRegion} />

      <DemoDatasetButton disabled={!selectedRegion || loadingText !== null} onClick={handleDemo} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--color-text-muted)', fontSize: 13 }}>
        <hr style={{ flex: 1, border: 'none', borderTop: '1px solid var(--color-border)' }} />
        или
        <hr style={{ flex: 1, border: 'none', borderTop: '1px solid var(--color-border)' }} />
      </div>

      <FileUploadForm disabled={!selectedRegion || loadingText !== null} onSubmit={handleUpload} />

      {loadingText && <LoadingOverlay text={loadingText} />}
      {error && <ErrorToast message={error} onDismiss={() => setError(null)} />}
    </div>
  );
}
