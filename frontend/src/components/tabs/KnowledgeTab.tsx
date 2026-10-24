import { useRef, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlineOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import MicIcon from "@mui/icons-material/Mic";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import GitHubIcon from "@mui/icons-material/GitHub";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSnackbar } from "notistack";
import { apiErrorMessage } from "../../api/client";
import {
  deleteSource,
  ingestGithub,
  ingestText,
  ingestVoiceNote,
  listSources,
  uploadSourceFile,
} from "../../api/endpoints";
import type { Visibility } from "../../api/types";
import { usePushToTalk } from "../../hooks/usePushToTalk";

const STATUS_ICON: Record<string, React.ReactElement> = {
  completed: <CheckCircleIcon fontSize="small" color="success" />,
  processing: <HourglassEmptyIcon fontSize="small" color="warning" />,
  pending: <HourglassEmptyIcon fontSize="small" color="warning" />,
  failed: <ErrorOutlineIcon fontSize="small" color="error" />,
};

const VISIBILITY_COLOR: Record<Visibility, "default" | "info" | "warning"> = {
  public: "default",
  friends: "info",
  private: "warning",
};

export default function KnowledgeTab({ twinId }: { twinId: string }) {
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [noteName, setNoteName] = useState("notes.txt");
  const [noteText, setNoteText] = useState("");
  const [noteVisibility, setNoteVisibility] = useState<Visibility>("public");
  const [fileVisibility, setFileVisibility] = useState<Visibility>("public");
  const [voiceVisibility, setVoiceVisibility] = useState<Visibility>("public");
  const [githubUsername, setGithubUsername] = useState("");
  const [githubVisibility, setGithubVisibility] = useState<Visibility>("public");

  const sourcesQuery = useQuery({ queryKey: ["sources", twinId], queryFn: () => listSources(twinId) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["sources", twinId] });

  const ingestTextMutation = useMutation({
    mutationFn: () => ingestText(twinId, noteName, noteText, noteVisibility),
    onSuccess: (source) => {
      invalidate();
      setNoteText("");
      enqueueSnackbar(`Ingested: ${source.chunk_count} chunk(s)`, { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const uploadFileMutation = useMutation({
    mutationFn: (file: File) => uploadSourceFile(twinId, file, fileVisibility),
    onSuccess: (source) => {
      invalidate();
      if (fileInputRef.current) fileInputRef.current.value = "";
      enqueueSnackbar(`Ingested: ${source.chunk_count} chunk(s)`, { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const voiceNoteMutation = useMutation({
    mutationFn: (blob: Blob) => ingestVoiceNote(twinId, blob, voiceVisibility),
    onSuccess: ({ source, transcript }) => {
      invalidate();
      enqueueSnackbar(`Captured: "${transcript.slice(0, 80)}${transcript.length > 80 ? "…" : ""}" (${source.chunk_count} chunk(s))`, {
        variant: "success",
      });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const githubMutation = useMutation({
    mutationFn: () => ingestGithub(twinId, githubUsername, githubVisibility),
    onSuccess: (source) => {
      invalidate();
      setGithubUsername("");
      enqueueSnackbar(`Imported @${source.name.split("@")[1] || githubUsername}: ${source.chunk_count} chunk(s)`, {
        variant: "success",
      });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const voicePushToTalk = usePushToTalk((message) => enqueueSnackbar(message, { variant: "error" }));
  const handleStopVoiceNote = async () => {
    const blob = await voicePushToTalk.stop();
    if (blob) voiceNoteMutation.mutate(blob);
  };

  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => deleteSource(twinId, sourceId),
    onSuccess: invalidate,
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  return (
    <Stack spacing={3}>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Add a text note
              </Typography>
              <Stack spacing={2}>
                <TextField label="Name" value={noteName} onChange={(e) => setNoteName(e.target.value)} fullWidth />
                <TextField
                  label="Content"
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  fullWidth
                  multiline
                  minRows={4}
                />
                <TextField
                  select
                  label="Visibility"
                  value={noteVisibility}
                  onChange={(e) => setNoteVisibility(e.target.value as Visibility)}
                  fullWidth
                >
                  <MenuItem value="public">Public</MenuItem>
                  <MenuItem value="friends">Friends</MenuItem>
                  <MenuItem value="private">Private</MenuItem>
                </TextField>
                <Box>
                  <Button
                    variant="contained"
                    disabled={!noteText.trim() || ingestTextMutation.isPending}
                    onClick={() => ingestTextMutation.mutate()}
                  >
                    {ingestTextMutation.isPending ? "Ingesting…" : "Ingest text"}
                  </Button>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Upload a file
              </Typography>
              <Stack spacing={2}>
                <Button
                  variant="outlined"
                  component="label"
                  startIcon={<UploadFileIcon />}
                  disabled={uploadFileMutation.isPending}
                >
                  {uploadFileMutation.isPending ? "Uploading…" : "Choose file (PDF / DOCX / TXT / MD)"}
                  <input
                    ref={fileInputRef}
                    type="file"
                    hidden
                    accept=".pdf,.docx,.txt,.md"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadFileMutation.mutate(file);
                    }}
                  />
                </Button>
                <TextField
                  select
                  label="Visibility"
                  value={fileVisibility}
                  onChange={(e) => setFileVisibility(e.target.value as Visibility)}
                  fullWidth
                >
                  <MenuItem value="public">Public</MenuItem>
                  <MenuItem value="friends">Friends</MenuItem>
                  <MenuItem value="private">Private</MenuItem>
                </TextField>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Add a voice note
              </Typography>
              <Stack spacing={2}>
                {!voicePushToTalk.isRecording ? (
                  <Button
                    variant="outlined"
                    startIcon={<MicIcon />}
                    onClick={voicePushToTalk.start}
                    disabled={voiceNoteMutation.isPending}
                  >
                    {voiceNoteMutation.isPending ? "Transcribing…" : "Start speaking"}
                  </Button>
                ) : (
                  <Button variant="contained" color="error" startIcon={<StopCircleIcon />} onClick={handleStopVoiceNote}>
                    Stop & save
                  </Button>
                )}
                <Typography variant="caption" color="text.secondary">
                  Speak naturally — it's transcribed and added as a source, same as typing a note.
                </Typography>
                <TextField
                  select
                  label="Visibility"
                  value={voiceVisibility}
                  onChange={(e) => setVoiceVisibility(e.target.value as Visibility)}
                  fullWidth
                >
                  <MenuItem value="public">Public</MenuItem>
                  <MenuItem value="friends">Friends</MenuItem>
                  <MenuItem value="private">Private</MenuItem>
                </TextField>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
                Import from GitHub
              </Typography>
              <Stack spacing={2}>
                <TextField
                  label="GitHub username"
                  placeholder="e.g. octocat"
                  value={githubUsername}
                  onChange={(e) => setGithubUsername(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && githubUsername.trim() && githubMutation.mutate()}
                  fullWidth
                />
                <Typography variant="caption" color="text.secondary">
                  Pulls the public profile and repo list — bio, pinned info, languages, stars.
                  LinkedIn isn't supported (its terms block scraping); paste a LinkedIn summary
                  into a text note instead.
                </Typography>
                <TextField
                  select
                  label="Visibility"
                  value={githubVisibility}
                  onChange={(e) => setGithubVisibility(e.target.value as Visibility)}
                  fullWidth
                >
                  <MenuItem value="public">Public</MenuItem>
                  <MenuItem value="friends">Friends</MenuItem>
                  <MenuItem value="private">Private</MenuItem>
                </TextField>
                <Box>
                  <Button
                    variant="contained"
                    startIcon={<GitHubIcon />}
                    disabled={!githubUsername.trim() || githubMutation.isPending}
                    onClick={() => githubMutation.mutate()}
                  >
                    {githubMutation.isPending ? "Importing…" : "Import"}
                  </Button>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box>
        <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
          Sources
        </Typography>
        {sourcesQuery.data?.length === 0 && (
          <Typography color="text.secondary">No sources yet — add one above.</Typography>
        )}
        <Stack spacing={1}>
          {sourcesQuery.data?.map((s) => (
            <Card key={s.id} variant="outlined">
              <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                  {STATUS_ICON[s.status]}
                  <Stack sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Typography noWrap fontWeight={500}>
                      {s.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {s.chunk_count} chunk(s)
                      {s.error_message ? ` — ${s.error_message}` : ""}
                    </Typography>
                  </Stack>
                  <Chip size="small" label={s.visibility} color={VISIBILITY_COLOR[s.visibility]} />
                  <Tooltip title="Delete">
                    <IconButton size="small" onClick={() => deleteMutation.mutate(s.id)}>
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      </Box>
    </Stack>
  );
}
