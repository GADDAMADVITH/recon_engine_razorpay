import { lazy, Suspense, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Sidebar, Topbar } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { ExceptionsPage } from "./pages/ExceptionsPage";
import { ReconciliationPage } from "./pages/ReconciliationPage";
import { SettingsPage } from "./pages/SettingsPage";

const LandingPage = lazy(() => import("./pages/LandingPage"));

function PageWrapper({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="page-enter">
      {children}
    </div>
  );
}

function ConsoleLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] lg:flex">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setSidebarOpen(true)} />
        <main className="flex-1 px-4 py-8 lg:px-10 lg:py-10">
          <PageWrapper>
            <Outlet />
          </PageWrapper>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Suspense fallback={<div className="marketing min-h-screen" />}>
            <LandingPage />
          </Suspense>
        }
      />
      <Route path="/console" element={<ConsoleLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="dashboard" element={<Navigate to="/console" replace />} />
        <Route path="reconciliation" element={<ReconciliationPage />} />
        <Route path="exceptions" element={<ExceptionsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
