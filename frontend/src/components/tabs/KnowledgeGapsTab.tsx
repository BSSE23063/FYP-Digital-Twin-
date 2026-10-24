import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import GroupsIcon from "@mui/icons-material/Groups";
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSnackbar } from "notistack";
import { apiErrorMessage } from "../../api/client";
import {
  analyzeKnowledgeGaps,
  confirmGapCluster,
  curateGapAnswer,
  dismissKnowledgeGap,
  listKnowledgeGaps,
} from "../../api/endpoints";
import type { GapCluster, KnowledgeGap, Visibility } from "../../api/types";
import EmptyState from "../EmptyState";

/** One clustered question from the Gap Analyst agent — the owner answers
 * once here (optionally cleaned up by the Curator agent) and it resolves
 * every grouped gap at once. Nothing is saved until "Save answer". */
function ClusterCard({ twinId, cluster }: { twinId: string; cluster: GapCluster }) {
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const [text, setText] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("public");
  const [reasoning, setReasoning] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["gaps", twinId] });
    queryClient.invalidateQueries({ queryKey: ["gaps", "clusters", twinId] });
  };

  const curateMutation = useMutation({
    mutationFn: () => curateGapAnswer(twinId, cluster.gap_ids, text),
    onSuccess: (draft) => {
      setText(draft.text);
      setVisibility(draft.suggested_visibility);
      setReasoning(draft.reasoning);
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const confirmMutation = useMutation({
    mutationFn: () => confirmGapCluster(twinId, cluster.gap_ids, text, visibility),
    onSuccess: () => {
      invalidate();
      enqueueSnackbar("Saved — now part of this twin's knowledge", { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const dismissMutation = useMutation({
    mutationFn: () => Promise.all(cluster.gap_ids.map((id) => dismissKnowledgeGap(twinId, id))),
    onSuccess: invalidate,
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Chip size="small" icon={<GroupsIcon />} label={cluster.theme} color="primary" variant="outlined" />
            <Typography variant="caption" color="text.secondary">
              {cluster.gap_ids.length} question{cluster.gap_ids.length === 1 ? "" : "s"} grouped here
            </Typography>
          </Stack>

          <Typography fontWeight={500}>{cluster.suggested_prompt}</Typography>

          <TextField
            label="Your answer"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setReasoning(null);
            }}
            multiline
            minRows={2}
            fullWidth
          />

          {reasoning && (
            <Alert severity="info" icon={<AutoAwesomeIcon fontSize="small" />} sx={{ py: 0 }}>
              {reasoning}
            </Alert>
          )}

          <Stack direction="row" spacing={2} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <TextField
              select
              size="small"
              label="Visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
              sx={{ minWidth: 150 }}
            >
              <MenuItem value="public">Public</MenuItem>
              <MenuItem value="friends">Friends</MenuItem>
              <MenuItem value="private">Private</MenuItem>
            </TextField>
            <Button
              size="small"
              startIcon={<AutoAwesomeIcon />}
              disabled={!text.trim() || curateMutation.isPending}
              onClick={() => curateMutation.mutate()}
            >
              {curateMutation.isPending ? "Cleaning up…" : "Clean up with AI"}
            </Button>
            <Button
              variant="contained"
              size="small"
              disabled={!text.trim() || confirmMutation.isPending}
              onClick={() => confirmMutation.mutate()}
            >
              Save answer
            </Button>
            <Button size="small" color="inherit" onClick={() => dismissMutation.mutate()}>
              Dismiss all
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

function GapCard({ twinId, gap }: { twinId: string; gap: KnowledgeGap }) {
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();

  const dismissMutation = useMutation({
    mutationFn: () => dismissKnowledgeGap(twinId, gap.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["gaps", twinId] }),
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1}>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <Typography fontWeight={500}>{gap.question_text}</Typography>
            <Chip
              size="small"
              label={gap.status}
              color={gap.status === "pending" ? "warning" : gap.status === "answered" ? "success" : "default"}
            />
          </Stack>
          {gap.status === "answered" && gap.answer_text && (
            <Typography variant="body2" color="text.secondary">
              <strong>A:</strong> {gap.answer_text}
            </Typography>
          )}
          {gap.status === "pending" && (
            <Box>
              <Button size="small" color="inherit" onClick={() => dismissMutation.mutate()}>
                Dismiss
              </Button>
            </Box>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function KnowledgeGapsTab({ twinId }: { twinId: string }) {
  const [status, setStatus] = useState("pending");

  const clustersQuery = useQuery({
    queryKey: ["gaps", "clusters", twinId],
    queryFn: () => analyzeKnowledgeGaps(twinId),
    enabled: status === "pending",
  });

  const gapsQuery = useQuery({
    queryKey: ["gaps", twinId, status],
    queryFn: () => listKnowledgeGaps(twinId, status === "all" ? undefined : status),
    enabled: status !== "pending",
  });

  return (
    <Stack spacing={2} sx={{ maxWidth: 760 }}>
      <Box sx={{ maxWidth: 220 }}>
        <TextField select label="Filter" value={status} onChange={(e) => setStatus(e.target.value)} fullWidth>
          <MenuItem value="pending">Pending</MenuItem>
          <MenuItem value="answered">Answered</MenuItem>
          <MenuItem value="dismissed">Dismissed</MenuItem>
          <MenuItem value="all">All</MenuItem>
        </TextField>
      </Box>

      {status === "pending" && (
        <>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="body2" color="text.secondary">
              Grouped by topic — answer once, resolve every related question.
            </Typography>
            <Tooltip title="These are questions visitors asked that this twin couldn't answer. The Analyst agent groups similar phrasings together so you're not answering the same thing three times.">
              <InfoOutlinedIcon fontSize="small" sx={{ color: "text.disabled", cursor: "help" }} />
            </Tooltip>
          </Stack>
          {clustersQuery.data?.length === 0 && (
            <EmptyState
              icon={HelpOutlineOutlinedIcon}
              title="Nothing pending"
              description="No unanswered questions right now — they'll show up here as visitors chat with this twin."
            />
          )}
          <Stack spacing={1.5}>
            {clustersQuery.data?.map((c) => (
              <ClusterCard key={c.gap_ids.join(",")} twinId={twinId} cluster={c} />
            ))}
          </Stack>
        </>
      )}

      {status !== "pending" && (
        <>
          {gapsQuery.data?.length === 0 && (
            <EmptyState icon={HelpOutlineOutlinedIcon} title="Nothing here" />
          )}
          <Stack spacing={1.5}>
            {gapsQuery.data?.map((g) => (
              <GapCard key={g.id} twinId={twinId} gap={g} />
            ))}
          </Stack>
        </>
      )}
    </Stack>
  );
}
