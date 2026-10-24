import { Avatar, Box, Button, Stack, Typography } from "@mui/material";
import CallEndIcon from "@mui/icons-material/CallEnd";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import type { CallStatus } from "../hooks/useVoiceCall";

const STATUS_LABEL: Record<CallStatus, string> = {
  idle: "Starting…",
  listening: "Listening — just start talking",
  thinking: "Thinking…",
  speaking: "Speaking…",
  error: "Something went wrong",
};

export default function CallOverlay({
  twinName,
  avatarUrl,
  status,
  volume,
  onEnd,
}: {
  twinName: string;
  avatarUrl?: string;
  status: CallStatus;
  volume: number;
  onEnd: () => void;
}) {
  // A gentle pulse driven by mic volume while listening, a steady pulse while
  // the twin is "speaking" (we can't measure its output volume the same way,
  // so this is just a calm animation, not a real level meter).
  const ringScale = status === "listening" ? 1 + Math.min(volume * 4, 0.5) : status === "speaking" ? 1.08 : 1;

  return (
    <Box
      sx={{
        minHeight: 420,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 3,
        py: 6,
      }}
    >
      <Box sx={{ position: "relative", width: 160, height: 160 }}>
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            bgcolor: status === "thinking" ? "warning.light" : "primary.light",
            opacity: 0.35,
            transform: `scale(${ringScale})`,
            transition: "transform 80ms linear",
          }}
        />
        <Avatar
          src={avatarUrl}
          sx={{
            width: 160,
            height: 160,
            bgcolor: "primary.main",
            fontSize: 56,
            border: "4px solid white",
            boxShadow: "0 4px 24px rgba(0,0,0,0.12)",
          }}
        >
          <SmartToyOutlinedIcon sx={{ fontSize: 64 }} />
        </Avatar>
      </Box>

      <Stack spacing={0.5} sx={{ alignItems: "center" }}>
        <Typography variant="h6">{twinName}</Typography>
        <Typography variant="body2" color="text.secondary">
          {STATUS_LABEL[status]}
        </Typography>
        {status === "thinking" && (
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 320, textAlign: "center" }}>
            This runs on CPU with no GPU — each reply takes real processing time
            (seconds, not instant). That's expected.
          </Typography>
        )}
      </Stack>

      <Button
        variant="contained"
        color="error"
        size="large"
        startIcon={<CallEndIcon />}
        onClick={onEnd}
        sx={{ borderRadius: 999, px: 4 }}
      >
        End call
      </Button>
    </Box>
  );
}
