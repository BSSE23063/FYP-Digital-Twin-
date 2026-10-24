import { ThemeProvider, CssBaseline } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SnackbarProvider } from "notistack";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { theme } from "./theme";
import { AuthProvider } from "./context/AuthContext";
import { useAuth } from "./context/useAuth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import VisitPage from "./pages/VisitPage";
import TwinDetailPage from "./pages/TwinDetailPage";
import ChatPage from "./pages/ChatPage";
import QdrantExplorerPage from "./pages/QdrantExplorerPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function RequireOwner({ children }: { children: React.ReactElement }) {
  const { isAuthenticated, role } = useAuth();
  if (!isAuthenticated || role !== "owner") return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <SnackbarProvider maxSnack={3} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<Layout />}>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/visit" element={<VisitPage />} />
                  <Route
                    path="/twins/:twinId"
                    element={
                      <RequireOwner>
                        <TwinDetailPage />
                      </RequireOwner>
                    }
                  />
                  <Route path="/twins/:twinId/chat" element={<ChatPage />} />
                  <Route
                    path="/debug/qdrant"
                    element={
                      <RequireOwner>
                        <QdrantExplorerPage />
                      </RequireOwner>
                    }
                  />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </QueryClientProvider>
      </SnackbarProvider>
    </ThemeProvider>
  );
}
