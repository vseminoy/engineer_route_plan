import { Navigate, Route, Routes } from 'react-router-dom';
import { DataLoadScreen } from '@/components/dataload/DataLoadScreen';
import { PlanScreen } from '@/components/plan/PlanScreen';

// Route tree per 06_spec_frontend.md §1. The ticket explanation is rendered
// as an overlay driven by useUiStore rather than its own
// /plan/:planId/ticket/:ticketId route — a deliberate simplification for
// this pass; it trades deep-linking/back-button support on that one screen
// for a simpler state model. Revisit if dispatchers need to share/bookmark
// a specific ticket's explanation.
export function App() {
  return (
    <Routes>
      <Route path="/" element={<DataLoadScreen />} />
      <Route path="/plan/:planId" element={<PlanScreen />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
