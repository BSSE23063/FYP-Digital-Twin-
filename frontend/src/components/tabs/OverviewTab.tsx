import { useRef, useState } from "react";
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useSnackbar } from "notistack";
import { API_BASE, apiErrorMessage } from "../../api/client";
import { deleteTwin, listSources, updateTwin, uploadAvatar, uploadVoiceSample } from "../../api/endpoints";
import type { Twin } from "../../api/types";
import VoiceSampleRecorder from "../VoiceSampleRecorder";

function StatusChip({ done, doneLabel, todoLabel }: { done: boolean; doneLabel: string; todoLabel: string }) {
  return (
    <Chip
      size="small"
      variant={done ? "filled" : "outlined"}
      color={done ? "success" : "default"}
      icon={done ? <CheckCircleIcon fontSize="small" /> : <RadioButtonUncheckedIcon fontSize="small" />}
      label={done ? doneLabel : todoLabel}
    />
  );
}

export default function OverviewTab({ twin }: { twin: Twin }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(twin.name);
  const [domain, setDomain] = useState(twin.domain);
  const [bio, setBio] = useState(twin.bio || "");
  const [persona, setPersona] = useState(twin.persona_prompt || "");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["twin", twin.id] });
    queryClient.invalidateQueries({ queryKey: ["twins"] });
  };

  const saveMutation = useMutation({
    mutationFn: () => updateTwin(twin.id, { name, domain, bio, persona_prompt: persona }),
    onSuccess: () => {
      invalidate();
      enqueueSnackbar("Saved", { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const avatarMutation = useMutation({
    mutationFn: (file: File) => uploadAvatar(twin.id, file),
    onSuccess: invalidate,
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const voiceMutation = useMutation({
    mutationFn: ({ file, filename, consent }: { file: Blob; filename: string; consent: boolean }) =>
      uploadVoiceSample(twin.id, file, filename, consent),
    onSuccess: () => {
      invalidate();
      enqueueSnackbar("Voice sample saved — replies will use this voice from now on", { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteTwin(twin.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["twins"] });
      navigate("/");
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const dirty =
    name !== twin.name ||
    domain !== twin.domain ||
    bio !== (twin.bio || "") ||
    persona !== (twin.persona_prompt || "");

  const sourcesQuery = useQuery({ queryKey: ["sources", twin.id], queryFn: () => listSources(twin.id) });
  const sourceCount = sourcesQuery.data?.length ?? 0;

  return (
    <Stack spacing={3} sx={{ maxWidth: 720 }}>
      <Card>
        <CardContent>
          <Stack direction="row" spacing={3} sx={{ alignItems: "center" }}>
            <Box sx={{ position: "relative" }}>
              <Avatar
                src={twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined}
                sx={{ width: 88, height: 88, bgcolor: "primary.light" }}
              >
                <SmartToyOutlinedIcon sx={{ fontSize: 40 }} />
              </Avatar>
              <IconButton
                size="small"
                onClick={() => fileInputRef.current?.click()}
                sx={{
                  position: "absolute",
                  bottom: -4,
                  right: -4,
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                  "&:hover": { bgcolor: "grey.100" },
                }}
              >
                <PhotoCameraIcon fontSize="small" />
              </IconButton>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) avatarMutation.mutate(file);
                }}
              />
            </Box>
            <Stack spacing={0.5}>
              <Typography variant="h6">{twin.name}</Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Chip size="small" label={twin.domain} color="primary" variant="outlined" />
                <Chip size="small" label={`@${twin.slug}`} variant="outlined" />
                <IconButton
                  size="small"
                  onClick={() => {
                    navigator.clipboard.writeText(twin.slug);
                    enqueueSnackbar("Handle copied", { variant: "success" });
                  }}
                >
                  <ContentCopyIcon fontSize="inherit" />
                </IconButton>
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Share this handle so people can find and chat with this twin.
              </Typography>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: "wrap" }}>
            <StatusChip done={Boolean(twin.avatar_url)} doneLabel="Photo added" todoLabel="No photo yet" />
            <StatusChip done={twin.has_voice_sample} doneLabel="Voice cloned" todoLabel="No voice yet" />
            <Chip
              size="small"
              variant="outlined"
              label={`${sourceCount} knowledge source${sourceCount === 1 ? "" : "s"}`}
            />
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
            Profile
          </Typography>
          <Stack spacing={2}>
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth />
            <TextField
              label="Domain / expertise"
              helperText="The one topic this twin knows about — it will only answer within this scope."
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              fullWidth
            />
            <TextField
              label="Short bio"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              fullWidth
              multiline
              minRows={2}
            />
            <TextField
              label="Persona instructions"
              helperText="How the twin should speak and behave — shapes every reply."
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              fullWidth
              multiline
              minRows={4}
            />
            <Box>
              <Button
                variant="contained"
                disabled={!dirty || !name.trim() || !domain.trim() || saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {saveMutation.isPending ? "Saving…" : "Save changes"}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2, alignItems: "center" }}>
            <Typography variant="subtitle1" fontWeight={600}>
              Voice
            </Typography>
            {twin.has_voice_sample && (
              <Chip
                size="small"
                icon={<CheckCircleIcon fontSize="small" />}
                label="Cloned"
                color="success"
                variant="outlined"
              />
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {twin.has_voice_sample
              ? "This twin replies in its own cloned voice. Record a new sample to replace it."
              : "This twin doesn't have its own voice yet — until one is added, it falls back to a generic voice."}
          </Typography>
          <VoiceSampleRecorder
            submitting={voiceMutation.isPending}
            submitLabel={twin.has_voice_sample ? "Replace voice" : "Save voice"}
            onSubmit={(file, filename, consent) => voiceMutation.mutate({ file, filename, consent })}
          />
        </CardContent>
      </Card>

      <Card sx={{ borderColor: "error.light" }}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }} color="error">
            Danger zone
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Deleting a twin removes all its knowledge, conversations, and access grants. This
            can't be undone.
          </Typography>
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            onClick={() => setConfirmDelete(true)}
          >
            Delete this twin
          </Button>
        </CardContent>
      </Card>

      <Dialog open={confirmDelete} onClose={() => setConfirmDelete(false)}>
        <DialogTitle>Delete "{twin.name}"?</DialogTitle>
        <DialogContent>
          <Typography color="text.secondary">
            This permanently deletes the twin, its knowledge base, conversations, and access
            grants. This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setConfirmDelete(false)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => deleteMutation.mutate()}>
            Delete permanently
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
