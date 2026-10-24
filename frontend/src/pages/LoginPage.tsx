import { useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import type { Role } from "../context/AuthContext";
import { useAuth } from "../context/useAuth";
import { apiErrorMessage } from "../api/client";
import { BRAND } from "../theme";

export default function LoginPage() {
  const { setRole, doLoginOwner, doRegisterOwner, doLoginVisitor } = useAuth();
  const navigate = useNavigate();

  const [role, setRoleTab] = useState<Role>("owner");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleRoleChange = (_: unknown, value: Role) => {
    setRoleTab(value);
    setRole(value);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (role === "owner") {
        if (mode === "login") await doLoginOwner(email, password);
        else await doRegisterOwner(email, password, displayName);
      } else {
        await doLoginVisitor(email, displayName || "Visitor");
      }
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        px: 2,
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: "-15%",
          background: BRAND.heroMesh,
          backgroundSize: "140% 140%",
          animation: "drift 18s ease-in-out infinite",
          zIndex: 0,
        }}
      />
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate("/")}
        sx={{ position: "absolute", top: 20, left: 20, color: "#fff", zIndex: 1, "&:hover": { bgcolor: "rgba(255,255,255,0.1)" } }}
      >
        Back
      </Button>

      <Card
        component={motion.div}
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        sx={{ maxWidth: 420, width: "100%", position: "relative", zIndex: 1 }}
      >
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} sx={{ mb: 3, alignItems: "center" }}>
            <Avatar sx={{ background: BRAND.gradient, width: 48, height: 48 }}>
              <AutoAwesomeIcon />
            </Avatar>
            <Typography variant="h5">Digital Twin</Typography>
            <Typography variant="body2" color="text.secondary" align="center">
              A grounded, access-controlled AI twin — sign in as its owner, or as a
              visitor it already knows.
            </Typography>
          </Stack>

          <Tabs value={role} onChange={handleRoleChange} variant="fullWidth" sx={{ mb: 2 }}>
            <Tab value="owner" label="Owner" />
            <Tab value="visitor" label="Visitor" />
          </Tabs>

          {role === "owner" && (
            <Tabs
              value={mode}
              onChange={(_, v) => setMode(v)}
              variant="fullWidth"
              sx={{ mb: 2 }}
              textColor="secondary"
              indicatorColor="secondary"
            >
              <Tab value="login" label="Log in" />
              <Tab value="register" label="Register" />
            </Tabs>
          )}

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {role === "visitor" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Passwordless — just an email. Or skip this and{" "}
              <Box component="span" sx={{ cursor: "pointer", fontWeight: 600 }} onClick={() => navigate("/visit")}>
                chat anonymously
              </Box>
              .
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                fullWidth
              />
              {(role === "visitor" || (role === "owner" && mode === "register")) && (
                <TextField
                  label="Display name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required={role === "owner"}
                  fullWidth
                />
              )}
              {role === "owner" && (
                <TextField
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  fullWidth
                />
              )}
              <Button type="submit" variant="contained" size="large" disabled={loading} fullWidth>
                {loading ? "Please wait…" : role === "owner" ? (mode === "login" ? "Log in" : "Create account") : "Continue"}
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
