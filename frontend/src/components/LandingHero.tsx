import { Box, Button, Chip, Stack, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BoltIcon from "@mui/icons-material/Bolt";
import VerifiedUserOutlinedIcon from "@mui/icons-material/VerifiedUserOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { BRAND } from "../theme";

const FEATURES = [
  {
    icon: VerifiedUserOutlinedIcon,
    label: "Grounded answers",
    description: "Replies are backed by real, cited knowledge — never a guess.",
  },
  {
    icon: GraphicEqIcon,
    label: "Cloned voice",
    description: "Each twin replies in its owner's own voice, not a generic TTS.",
  },
  {
    icon: BoltIcon,
    label: "Tiered access",
    description: "Public, friends, or private — visitors see only what they're granted.",
  },
];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12, delayChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: "easeOut" } },
};

/** The app's landing page content — a hero card (not full-viewport-bleed,
 * to stay consistent with the rest of the app's contained/rounded-card
 * layout rather than breaking out of Layout's max-width container) sitting
 * above the twin gallery on the visitor-facing dashboard. */
export default function LandingHero({ onBrowse }: { onBrowse: () => void }) {
  const navigate = useNavigate();

  return (
    <Box
      component={motion.div}
      initial="hidden"
      animate="show"
      variants={container}
      sx={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 6,
        mb: 5,
        px: { xs: 3, sm: 5, md: 7 },
        py: { xs: 5, sm: 7, md: 9 },
        color: "#fff",
        isolation: "isolate",
      }}
    >
      <Box
        sx={{
          position: "absolute",
          inset: "-15%",
          background: BRAND.heroMesh,
          backgroundSize: "140% 140%",
          animation: "drift 18s ease-in-out infinite",
          zIndex: -1,
        }}
      />

      <Stack spacing={2.5} sx={{ maxWidth: 620 }}>
        <Box component={motion.div} variants={item} sx={{ display: "flex" }}>
          <Chip
            icon={<AutoAwesomeIcon sx={{ color: "#fff !important" }} />}
            label="Grounded AI Digital Twins"
            sx={{
              bgcolor: "rgba(255,255,255,0.12)",
              color: "#fff",
              fontWeight: 700,
              border: "1px solid rgba(255,255,255,0.2)",
            }}
          />
        </Box>

        <Typography component={motion.h1} variants={item} variant="h3" sx={{ fontWeight: 800, lineHeight: 1.15, m: 0 }}>
          Talk to someone's knowledge,
          <br /> not a chatbot.
        </Typography>

        <Typography component={motion.p} variants={item} variant="body1" sx={{ color: "rgba(255,255,255,0.82)", maxWidth: 520, m: 0 }}>
          Every T2-RAG twin answers from its owner's real documents, in their own
          cloned voice — grounded, cited, and access-controlled, never a hallucinated
          guess.
        </Typography>

        <Box component={motion.div} variants={item}>
          <Stack direction="row" spacing={1.5} sx={{ pt: 1, flexWrap: "wrap", gap: 1.5 }}>
            <Button
              variant="contained"
              size="large"
              onClick={onBrowse}
              sx={{ bgcolor: "#fff", color: "primary.dark", "&:hover": { bgcolor: "rgba(255,255,255,0.88)" } }}
            >
              Browse twins
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate("/login")}
              sx={{
                borderColor: "rgba(255,255,255,0.4)",
                color: "#fff",
                "&:hover": { borderColor: "#fff", bgcolor: "rgba(255,255,255,0.08)" },
              }}
            >
              Create your own
            </Button>
          </Stack>
        </Box>
      </Stack>

      <Box component={motion.div} variants={item} sx={{ mt: { xs: 5, md: 7 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          {FEATURES.map((f) => (
            <Stack
              key={f.label}
              spacing={0.75}
              sx={{
                flex: 1,
                p: 2.25,
                borderRadius: 4,
                bgcolor: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.14)",
              }}
            >
              <f.icon sx={{ color: BRAND.primaryLight }} />
              <Typography variant="subtitle2" sx={{ color: "#fff" }}>
                {f.label}
              </Typography>
              <Typography variant="caption" sx={{ color: "rgba(255,255,255,0.7)" }}>
                {f.description}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Box>
    </Box>
  );
}
