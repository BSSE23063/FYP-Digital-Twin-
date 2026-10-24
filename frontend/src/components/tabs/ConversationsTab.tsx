import { useState } from "react";
import {
  Avatar,
  Box,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import MicIcon from "@mui/icons-material/Mic";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutlineOutlined";
import { useQuery } from "@tanstack/react-query";
import { getConversation, listConversations } from "../../api/endpoints";
import type { ConversationSummary, Visibility } from "../../api/types";
import ChatBubble from "../ChatBubble";
import EmptyState from "../EmptyState";

const TIER_COLOR: Record<Visibility, "default" | "info" | "warning"> = {
  public: "default",
  friends: "info",
  private: "warning",
};

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function ConversationRow({ conv, onClick }: { conv: ConversationSummary; onClick: () => void }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        p: 1.5,
        borderRadius: 2,
        cursor: "pointer",
        border: "1px solid",
        borderColor: "divider",
        "&:hover": { borderColor: "primary.main", bgcolor: "#FAFAFF" },
      }}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
        <Avatar sx={{ width: 36, height: 36, bgcolor: "primary.light" }}>
          {conv.channel === "voice" ? <MicIcon fontSize="small" /> : <ChatBubbleOutlineIcon fontSize="small" />}
        </Avatar>
        <Stack sx={{ flexGrow: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="body2" fontWeight={600} noWrap>
              {conv.is_owner_session ? "You (testing)" : conv.visitor_name}
            </Typography>
            <Chip size="small" label={conv.access_tier} color={TIER_COLOR[conv.access_tier as Visibility]} />
          </Stack>
          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
            {conv.last_message_preview || "No messages yet"}
          </Typography>
        </Stack>
        <Stack sx={{ alignItems: "flex-end", flexShrink: 0 }}>
          <Typography variant="caption" color="text.secondary">
            {timeAgo(conv.created_at)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {conv.message_count} msg{conv.message_count === 1 ? "" : "s"}
          </Typography>
        </Stack>
      </Stack>
    </Box>
  );
}

export default function ConversationsTab({ twinId }: { twinId: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["conversations", twinId],
    queryFn: () => listConversations(twinId),
  });

  const detailQuery = useQuery({
    queryKey: ["conversations", twinId, selectedId],
    queryFn: () => getConversation(twinId, selectedId as string),
    enabled: Boolean(selectedId),
  });

  if (selectedId) {
    const conv = detailQuery.data;
    return (
      <Box sx={{ maxWidth: 720 }}>
        <Stack direction="row" spacing={1} sx={{ mb: 2, alignItems: "center" }}>
          <IconButton size="small" onClick={() => setSelectedId(null)}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
          <Typography variant="subtitle1" fontWeight={600}>
            {conv?.is_owner_session ? "You (testing)" : conv?.visitor_name || "Conversation"}
          </Typography>
          {conv && <Chip size="small" label={conv.access_tier} color={TIER_COLOR[conv.access_tier as Visibility]} />}
        </Stack>

        {detailQuery.isLoading && <CircularProgress size={20} />}

        <Stack spacing={1.5}>
          {conv?.messages.map((m) => (
            <ChatBubble
              key={m.id}
              message={{
                id: m.id,
                role: m.role === "visitor" ? "user" : "assistant",
                text: m.content,
                meta:
                  m.role === "twin" && m.policy_decision
                    ? `${m.policy_decision}${m.confidence_score != null ? ` · ${Math.round(m.confidence_score * 100)}% confidence` : ""}`
                    : undefined,
              }}
            />
          ))}
        </Stack>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 720 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Everyone who has talked to this twin, not just the questions that got escalated to Knowledge Gaps.
      </Typography>

      {listQuery.isLoading && <CircularProgress size={20} />}

      {listQuery.data?.length === 0 && (
        <EmptyState
          icon={ForumOutlinedIcon}
          title="No conversations yet"
          description="Once someone chats with this twin, every conversation will show up here."
        />
      )}

      <Stack spacing={1}>
        {listQuery.data?.map((c) => (
          <ConversationRow key={c.id} conv={c} onClick={() => setSelectedId(c.id)} />
        ))}
      </Stack>
    </Box>
  );
}
