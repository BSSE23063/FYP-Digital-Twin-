import { AppBar, Avatar, Box, Button, Chip, Stack, Toolbar, Typography } from "@mui/material";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlineOutlined";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { BRAND } from "../theme";
import PageTransition from "./PageTransition";

export default function Layout() {
  const { role, email, displayName, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar position="sticky" color="inherit">
        <Toolbar sx={{ gap: 2 }}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ cursor: "pointer", flexGrow: 1, alignItems: "center" }}
            onClick={() => navigate("/")}
          >
            <Avatar sx={{ background: BRAND.gradient, width: 32, height: 32, fontSize: 15, fontWeight: 700 }}>
              T2
            </Avatar>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Digital Twin
            </Typography>
          </Stack>

          {isAuthenticated ? (
            <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
              <Chip
                size="small"
                icon={<PersonOutlineIcon />}
                label={`${role === "owner" ? "Owner" : "Visitor"} · ${displayName || email}`}
                variant="outlined"
              />
              <Button variant="outlined" size="small" onClick={() => { logout(); navigate("/login"); }}>
                Log out
              </Button>
            </Stack>
          ) : (
            <Button variant="contained" size="small" onClick={() => navigate("/login")}>
              Log in
            </Button>
          )}
        </Toolbar>
      </AppBar>

      <Box component="main" sx={{ maxWidth: 1280, mx: "auto", px: { xs: 2, md: 4 }, py: 4 }}>
        <PageTransition />
      </Box>
    </Box>
  );
}
