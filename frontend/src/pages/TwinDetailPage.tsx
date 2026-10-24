import { useState } from "react";
import { Avatar, Badge, Box, Button, Stack, Typography } from "@mui/material";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlineOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import GroupAddOutlinedIcon from "@mui/icons-material/GroupAddOutlined";
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigate, useParams } from "react-router-dom";
import { API_BASE } from "../api/client";
import { getTwin, listKnowledgeGaps } from "../api/endpoints";
import OverviewTab from "../components/tabs/OverviewTab";
import KnowledgeTab from "../components/tabs/KnowledgeTab";
import GrantsTab from "../components/tabs/GrantsTab";
import KnowledgeGapsTab from "../components/tabs/KnowledgeGapsTab";
import ConversationsTab from "../components/tabs/ConversationsTab";

const TABS = ["overview", "knowledge", "conversations", "grants", "gaps"] as const;
type TabKey = (typeof TABS)[number];

export default function TwinDetailPage() {
  const { twinId } = useParams<{ twinId: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("overview");

  const twinQuery = useQuery({
    queryKey: ["twin", twinId],
    queryFn: () => getTwin(twinId!),
    enabled: Boolean(twinId),
  });

  const pendingGapsQuery = useQuery({
    queryKey: ["gaps", twinId, "pending", "count"],
    queryFn: () => listKnowledgeGaps(twinId!, "pending"),
    enabled: Boolean(twinId),
  });

  if (!twinId || twinQuery.isLoading) return <Typography color="text.secondary">Loading…</Typography>;
  if (!twinQuery.data) return <Typography color="error">Twin not found.</Typography>;
  const twin = twinQuery.data;
  const pendingCount = pendingGapsQuery.data?.length ?? 0;

  const NAV_ITEMS: { key: TabKey; label: string; icon: typeof PersonOutlineIcon; badge?: number }[] = [
    { key: "overview", label: "Overview", icon: PersonOutlineIcon },
    { key: "knowledge", label: "Knowledge", icon: MenuBookOutlinedIcon },
    { key: "conversations", label: "Conversations", icon: ForumOutlinedIcon },
    { key: "grants", label: "Access Grants", icon: GroupAddOutlinedIcon },
    { key: "gaps", label: "Knowledge Gaps", icon: HelpOutlineOutlinedIcon, badge: pendingCount },
  ];

  return (
    <Box>
      <Stack direction="row" sx={{ mb: 2.5, alignItems: "center", justifyContent: "space-between" }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/")} color="inherit" size="small">
          All twins
        </Button>
        <Button
          variant="contained"
          startIcon={<ChatBubbleOutlineIcon />}
          onClick={() => navigate(`/twins/${twin.id}/chat`)}
        >
          Open chat
        </Button>
      </Stack>

      <Stack direction="row" spacing={3} sx={{ alignItems: "flex-start" }}>
        <Stack sx={{ width: 232, flexShrink: 0 }} spacing={2}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", px: 0.5 }}>
            <Avatar
              src={twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined}
              sx={{ width: 40, height: 40, bgcolor: "primary.light" }}
            >
              <SmartToyOutlinedIcon fontSize="small" />
            </Avatar>
            <Stack sx={{ minWidth: 0 }}>
              <Typography variant="subtitle1" fontWeight={700} noWrap>
                {twin.name}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>
                {twin.domain}
              </Typography>
            </Stack>
          </Stack>

          <Stack spacing={0.5}>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const selected = tab === item.key;
              return (
                <Box
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  sx={{
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    gap: 1.25,
                    px: 1.5,
                    py: 1,
                    borderRadius: 2,
                    cursor: "pointer",
                    color: selected ? "primary.main" : "text.secondary",
                    fontWeight: selected ? 700 : 500,
                    "&:hover": { bgcolor: selected ? "transparent" : "#F5F6FA" },
                  }}
                >
                  {selected && (
                    <Box
                      component={motion.div}
                      layoutId="nav-active-pill"
                      transition={{ type: "spring", stiffness: 500, damping: 36 }}
                      sx={{ position: "absolute", inset: 0, borderRadius: 2, bgcolor: "#EEF2FF", zIndex: 0 }}
                    />
                  )}
                  <Icon fontSize="small" sx={{ position: "relative", zIndex: 1 }} />
                  <Typography variant="body2" fontWeight="inherit" sx={{ position: "relative", zIndex: 1, flexGrow: 1 }}>
                    {item.label}
                  </Typography>
                  {!!item.badge && (
                    <Badge
                      badgeContent={item.badge}
                      color="warning"
                      sx={{ position: "relative", zIndex: 1, "& .MuiBadge-badge": { position: "static", transform: "none" } }}
                    />
                  )}
                </Box>
              );
            })}
          </Stack>
        </Stack>

        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              {tab === "overview" && <OverviewTab twin={twin} />}
              {tab === "knowledge" && <KnowledgeTab twinId={twin.id} />}
              {tab === "conversations" && <ConversationsTab twinId={twin.id} />}
              {tab === "grants" && <GrantsTab twinId={twin.id} />}
              {tab === "gaps" && <KnowledgeGapsTab twinId={twin.id} />}
            </motion.div>
          </AnimatePresence>
        </Box>
      </Stack>
    </Box>
  );
}
