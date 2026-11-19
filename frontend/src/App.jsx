import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./AuthContext";
import Layout from "./components/Layout";
import ChatPage from "./pages/ChatPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-shell muted">در حال بارگذاری…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
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
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
