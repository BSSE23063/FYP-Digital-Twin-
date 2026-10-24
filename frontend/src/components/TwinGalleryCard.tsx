import { Box, Card, CardActionArea, Chip, Stack, Typography } from "@mui/material";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import { API_BASE } from "../api/client";
import type { Twin } from "../api/types";

/** The visitor-facing discovery card — click it, start talking, no handle or
 * ID required. Styled after full-bleed "talk to X" avatar cards: the photo
 * fills the card, the name/bio sit over a gradient, and hovering reveals the
 * CTA — a twin is something you browse and pick, not something you look up. */
export default function TwinGalleryCard({ twin, onClick }: { twin: Twin; onClick: () => void }) {
  const avatarSrc = twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined;

  return (
    <Card sx={{ borderRadius: 3, overflow: "hidden" }}>
      <CardActionArea
        onClick={onClick}
        sx={{
          position: "relative",
          height: 280,
          "&:hover .talk-cta": { opacity: 1, transform: "translateY(0)" },
        }}
      >
        {avatarSrc ? (
          <Box
            component="img"
            src={avatarSrc}
            alt={twin.name}
            sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <Box
            sx={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              bgcolor: "primary.light",
            }}
          >
            <SmartToyOutlinedIcon sx={{ fontSize: 64, color: "primary.contrastText" }} />
          </Box>
        )}

        {twin.has_voice_sample && (
          <Chip
            size="small"
            icon={<GraphicEqIcon sx={{ fontSize: 14 }} />}
            label="Voice"
            sx={{
              position: "absolute",
              top: 10,
              right: 10,
              bgcolor: "rgba(0,0,0,0.55)",
              color: "#fff",
              "& .MuiChip-icon": { color: "#fff" },
            }}
          />
        )}

        <Box
          sx={{
            position: "absolute",
            inset: 0,
            background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.15) 55%, transparent 100%)",
          }}
        />

        <Stack sx={{ position: "absolute", left: 16, right: 16, bottom: 16, color: "#fff" }} spacing={0.5}>
          <Typography variant="subtitle1" fontWeight={700} noWrap>
            {twin.name}
          </Typography>
          <Chip
            size="small"
            label={twin.domain}
            sx={{
              alignSelf: "flex-start",
              bgcolor: "rgba(255,255,255,0.18)",
              color: "#fff",
              fontWeight: 600,
            }}
          />
          {twin.bio && (
            <Typography variant="caption" sx={{ opacity: 0.85 }} noWrap>
              {twin.bio}
            </Typography>
          )}
        </Stack>

        <Stack
          className="talk-cta"
          direction="row"
          spacing={0.75}
          sx={{
            position: "absolute",
            left: 16,
            top: 16,
            alignItems: "center",
            bgcolor: "rgba(255,255,255,0.95)",
            color: "primary.main",
            px: 1.25,
            py: 0.5,
            borderRadius: 5,
            opacity: { xs: 1, sm: 0 },
            transform: { xs: "none", sm: "translateY(-4px)" },
            transition: "opacity 0.15s ease, transform 0.15s ease",
          }}
        >
          <ChatBubbleOutlineIcon sx={{ fontSize: 16 }} />
          <Typography variant="caption" fontWeight={700}>
            Talk to {twin.name.split(" ")[0]}
          </Typography>
        </Stack>
      </CardActionArea>
    </Card>
  );
}
