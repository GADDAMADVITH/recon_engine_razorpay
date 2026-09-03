import { lazy, Suspense, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { ReconAIChat } from "./components/chat/ReconAIChat";
import { ConsoleAtmosphere, Sidebar, Topbar } from "./components/layout/AppShell";
import { ChatOrderProvider } from "./context/ChatOrderContext";
import { ConsoleReportProvider } from "./context/ConsoleReportContext";
import { BankImportPage } from "./pages/BankImportPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { ExceptionsPage } from "./pages/ExceptionsPage";
import { ReconciliationPage } from "./pages/ReconciliationPage";
import { SettingsPage } from "./pages/SettingsPage";

const LandingPage = lazy(() => import("./pages/LandingPage"));
const TestPaymentPage = lazy(() => import("./test-payment/TestPaymentPage"));

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
    <ConsoleReportProvider>
      <ChatOrderProvider>
        <div className="min-h-screen bg-[var(--color-bg)] lg:flex">
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
          <div className="relative flex min-h-screen min-w-0 flex-1 flex-col overflow-hidden">
            <ConsoleAtmosphere />
            <Topbar onMenuClick={() => setSidebarOpen(true)} />
            <main className="relative z-10 flex-1 px-5 py-10 lg:px-12 lg:py-12">
              <PageWrapper>
                <Outlet />
              </PageWrapper>
            </main>
            <ReconAIChat />
          </div>
        </div>
      </ChatOrderProvider>
    </ConsoleReportProvider>
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
      <Route
        path="/test-payment"
        element={
          <Suspense fallback={<div className="min-h-screen bg-[var(--color-bg)]" />}>
            <TestPaymentPage />
          </Suspense>
        }
      />
      <Route path="/console" element={<ConsoleLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="dashboard" element={<Navigate to="/console" replace />} />
        <Route path="reconciliation" element={<ReconciliationPage />} />
        <Route path="exceptions" element={<ExceptionsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="bank-import" element={<BankImportPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
