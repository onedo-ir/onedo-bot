import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./AuthContext";
import Layout from "./components/Layout";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";
import SchedulesPage from "./pages/SchedulesPage";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-shell muted">در حال بارگذاری…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-shell muted">در حال بارگذاری…</div>;
  if (user) return <Navigate to="/app" replace />;
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/app"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<ChatPage />} />
        <Route path="schedules" element={<SchedulesPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
