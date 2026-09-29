import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { RegionSelect } from './RegionSelect';
import { FileUploadForm } from './FileUploadForm';
import { DemoDatasetButton } from './DemoDatasetButton';
import { DataLoadSummary } from './DataLoadSummary';
import { LoadingOverlay } from '@/components/common/LoadingOverlay';
import { ErrorToast } from '@/components/common/ErrorToast';
import { loadDemoDataset, uploadDataset } from '@/api/endpoints';
import { useBuildPlan } from '@/queries/useBuildPlan';
import { useUiStore } from '@/store/useUiStore';
import { queryKeys } from '@/queries/keys';
import { describeError } from '@/lib/labels';
import { fieldErrorsFromApi, fieldErrorsFromZod, isFieldErrors, type FieldErrorMap } from '@/lib/fieldErrors';
import { ApiError } from '@/api/client';
import { UploadRegionDataBody } from '@/api/generated/zod/engineerRoutePlanAPI';
import type { DataLoadResult, RegionCode } from '@/types/domain';

// Fixed demo day across all three regions' synthetic datasets.
const PLAN_DATE = '2026-08-17';

const regionField = UploadRegionDataBody.shape.region;

export function DataLoadScreen() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const selectedRegion = useUiStore((s) => s.selectedRegion);
  const setSelectedRegion = useUiStore((s) => s.setSelectedRegion);
  const buildPlanMutation = useBuildPlan();
  const [loadingText, setLoadingText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrorMap>({});
  const [loadResult, setLoadResult] = useState<DataLoadResult | null>(null);

  function setFieldError(field: string, message: string | null) {
    setFieldErrors((prev) => {
      if (message === null) {
        if (!(field in prev)) return prev;
        const next = { ...prev };
        delete next[field];
        return next;
      }
      return { ...prev, [field]: message };
    });
  }

  function validateRegion(): boolean {
    const result = regionField.safeParse(selectedRegion ?? '');
    setFieldError('region', result.success ? null : (result.error.issues[0]?.message ?? 'Некорректный регион'));
    return result.success;
  }

  async function runBuild() {
    if (!selectedRegion) return;
    setLoadResult(null);
    setLoadingText('Строим план…');
    try {
      const { main } = await buildPlanMutation.mutateAsync({ region: selectedRegion, planDate: PLAN_DATE });
      navigate(`/plan/${main.planId}`);
    } catch (err) {
      setError(describeError(err, 'POST /plan/build'));
      setLoadingText(null);
    }
  }

  async function afterLoad(region: RegionCode, result: DataLoadResult) {
    queryClient.invalidateQueries({ queryKey: queryKeys.tickets(region) });
    queryClient.invalidateQueries({ queryKey: queryKeys.engineers(region) });
    if (result.invalidRows.length === 0) {
      await runBuild();
    } else {
      setLoadResult(result);
      setLoadingText(null);
    }
  }

  async function handleDemo() {
    if (!selectedRegion) return;
    setError(null);
    if (!validateRegion()) return;
    setLoadingText('Загружаем демо-набор…');
    try {
      const result = await loadDemoDataset(selectedRegion);
      await afterLoad(selectedRegion, result);
    } catch (err) {
      handleLoadError(err, 'POST /data/demo');
    }
  }

  async function handleUpload(ticketsFile: File) {
    if (!selectedRegion) return;
    setError(null);
    const regionOk = validateRegion();
    const parsed = UploadRegionDataBody.safeParse({ region: selectedRegion, tickets_file: ticketsFile });
    if (!regionOk || !parsed.success) {
      if (!parsed.success) setFieldErrors((prev) => ({ ...prev, ...fieldErrorsFromZod(parsed.error) }));
      return;
    }
    setLoadingText('Загружаем файл…');
    try {
      const result = await uploadDataset(selectedRegion, ticketsFile);
      await afterLoad(selectedRegion, result);
    } catch (err) {
      handleLoadError(err, 'POST /data/upload');
    }
  }

  function handleLoadError(err: unknown, endpoint: string) {
    if (err instanceof ApiError && err.status === 400 && err.body) {
      const body = err.body;
      if (isFieldErrors(body)) {
        setFieldErrors((prev) => ({ ...prev, ...fieldErrorsFromApi(body) }));
      } else {
        setFieldError('tickets_file', body.message);
      }
    } else {
      setError(describeError(err, endpoint));
    }
    setLoadingText(null);
  }

  return (
    <div style={{ maxWidth: 480, margin: '64px auto', padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Диспетчер маршрутов</h1>

      {loadResult ? (
        <DataLoadSummary result={loadResult} onBuild={runBuild} onDismiss={() => setLoadResult(null)} />
      ) : (
        <>
          <RegionSelect
            value={selectedRegion}
            onChange={setSelectedRegion}
            onBlur={validateRegion}
            error={fieldErrors.region}
          />

          <DemoDatasetButton disabled={!selectedRegion || loadingText !== null} onClick={handleDemo} />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--color-text-muted)', fontSize: 13 }}>
            <hr style={{ flex: 1, border: 'none', borderTop: '1px solid var(--color-border)' }} />
            или
            <hr style={{ flex: 1, border: 'none', borderTop: '1px solid var(--color-border)' }} />
          </div>

          <FileUploadForm
            disabled={!selectedRegion || loadingText !== null}
            error={fieldErrors.tickets_file}
            onFileSelected={(_file, message) => setFieldError('tickets_file', message)}
            onSubmit={handleUpload}
          />
        </>
      )}

      {loadingText && <LoadingOverlay text={loadingText} />}
      {error && <ErrorToast message={error} onDismiss={() => setError(null)} />}
    </div>
  );
}
