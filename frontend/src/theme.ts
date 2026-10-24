import { createTheme } from "@mui/material/styles";

// A few raw values reused outside the theme object itself (gradients, the
// sidebar's own surface) — kept here once rather than re-typed at each call
// site.
export const BRAND = {
  primary: "#4F46E5",
  primaryDark: "#3730A3",
  primaryLight: "#818CF8",
  secondary: "#0D9488",
  accent: "#F59E0B",
  gradient: "linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #0D9488 100%)",
  // Landing-page hero background (session 24) — three soft, slowly-drifting
  // radial blobs rather than a flat gradient, animated via the `drift`
  // keyframes registered on MuiCssBaseline below.
  heroMesh: `
    radial-gradient(circle at 15% 20%, rgba(99,102,241,0.35), transparent 45%),
    radial-gradient(circle at 85% 15%, rgba(13,148,136,0.28), transparent 45%),
    radial-gradient(circle at 50% 85%, rgba(245,158,11,0.18), transparent 50%),
    #0B0F1A
  `,
};

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: BRAND.primary, light: BRAND.primaryLight, dark: BRAND.primaryDark },
    secondary: { main: BRAND.secondary },
    background: { default: "#F7F8FB", paper: "#FFFFFF" },
    text: { primary: "#171A23", secondary: "#636B7D" },
    divider: "#E7E9F0",
    success: { main: "#16A34A" },
    warning: { main: "#D97706" },
    error: { main: "#DC2626" },
  },
  shape: { borderRadius: 14 },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontWeight: 700, letterSpacing: "-0.02em" },
    h2: { fontWeight: 700, letterSpacing: "-0.02em" },
    h3: { fontWeight: 700, letterSpacing: "-0.015em" },
    h4: { fontWeight: 700, letterSpacing: "-0.01em" },
    h5: { fontWeight: 700, letterSpacing: "-0.01em" },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { fontWeight: 600 },
    body2: { lineHeight: 1.6 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "::selection": { backgroundColor: "#C7D2FE" },
        "*": { scrollbarWidth: "thin", scrollbarColor: "#D1D5E0 transparent" },
        "*::-webkit-scrollbar": { width: 8, height: 8 },
        "*::-webkit-scrollbar-thumb": { backgroundColor: "#D1D5E0", borderRadius: 8 },
        // Registered globally once, reused by every slow-moving decorative
        // background (the landing hero, the login page) rather than redefined
        // per component — a plain CSS animation, not framer-motion, since it
        // just loops forever with no state to drive.
        "@keyframes drift": {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(2%, -3%, 0) scale(1.05)" },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", borderRadius: 10, fontWeight: 600 },
        containedPrimary: {
          boxShadow: "0 1px 2px rgba(79,70,229,0.25)",
          "&:hover": { boxShadow: "0 4px 12px rgba(79,70,229,0.32)" },
        },
        sizeLarge: { paddingTop: 10, paddingBottom: 10, fontSize: "0.95rem" },
      },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: "none" } },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid #E7E9F0",
          boxShadow: "0 1px 3px rgba(23,26,35,0.04)",
          borderRadius: 16,
        },
      },
    },
    MuiCardActionArea: {
      styleOverrides: {
        root: {
          transition: "transform 0.15s ease, box-shadow 0.15s ease",
          "&:hover": { transform: "translateY(-2px)", boxShadow: "0 8px 24px rgba(23,26,35,0.10)" },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600, borderRadius: 8 },
      },
    },
    MuiTextField: {
      defaultProps: { size: "small" },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { borderRadius: 10 },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: "none",
          borderBottom: "1px solid #E7E9F0",
          backgroundColor: "rgba(255,255,255,0.86)",
          backdropFilter: "blur(10px)",
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: { height: 3, borderRadius: 3 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600, minHeight: 44 },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 18 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { fontSize: "0.75rem", borderRadius: 8 },
      },
    },
  },
});
