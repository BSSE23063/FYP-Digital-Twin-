import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, FormControlLabel, Stack, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import ReplayIcon from "@mui/icons-material/Replay";
import { usePushToTalk } from "../hooks/usePushToTalk";

/** Shared "give this twin its own voice" capture: record ~10-30s live, or
 * upload a clip — either way it's the reference clone the TTS model clones
 * from (backend/voice/tts.py), so consent is a required, explicit checkbox,
 * not a pre-ticked box. Used both at twin creation (mandatory) and later from
 * the Overview tab (to add/replace it). */
export default function VoiceSampleRecorder({
  onSubmit,
  submitting,
  submitLabel = "Save voice",
}: {
  onSubmit: (file: Blob, filename: string, consent: boolean) => void;
  submitting: boolean;
  submitLabel?: string;
}) {
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pushToTalk = usePushToTalk((message) => setError(message));
  const [error, setError] = useState<string | null>(null);

  const clip = uploadedFile ?? recordedBlob;

  useEffect(() => {
    if (!clip) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(clip);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [clip]);

  useEffect(() => {
    if (pushToTalk.isRecording) {
      const start = Date.now();
      timerRef.current = setInterval(() => setElapsedMs(Date.now() - start), 200);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [pushToTalk.isRecording]);

  const reset = () => {
    setRecordedBlob(null);
    setUploadedFile(null);
    setElapsedMs(0);
  };

  const handleStopRecording = async () => {
    const blob = await pushToTalk.stop();
    if (blob) setRecordedBlob(blob);
  };

  const handleSubmit = () => {
    if (!clip || !consent) return;
    const filename = uploadedFile?.name || "voice-sample.webm";
    onSubmit(clip, filename, consent);
  };

  return (
    <Stack spacing={2}>
      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {!clip && !pushToTalk.isRecording && (
        <Stack direction="row" spacing={1.5}>
          <Button variant="contained" startIcon={<MicIcon />} onClick={pushToTalk.start}>
            Record my voice
          </Button>
          <Button variant="outlined" startIcon={<UploadFileIcon />} onClick={() => fileInputRef.current?.click()}>
            Upload a clip
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) setUploadedFile(file);
            }}
          />
        </Stack>
      )}

      {pushToTalk.isRecording && (
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Button
            variant="contained"
            color="error"
            startIcon={<StopCircleIcon />}
            onClick={handleStopRecording}
          >
            Stop recording
          </Button>
          <Typography variant="body2" color="text.secondary">
            {(elapsedMs / 1000).toFixed(0)}s — aim for 10–30s of just you talking
          </Typography>
        </Stack>
      )}

      {clip && !pushToTalk.isRecording && (
        <Stack spacing={1.5}>
          <Box>
            <audio controls src={previewUrl || undefined} style={{ height: 36, width: "100%" }} />
          </Box>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <Button size="small" startIcon={<ReplayIcon />} onClick={reset}>
              Start over
            </Button>
          </Stack>
        </Stack>
      )}

      <FormControlLabel
        control={<Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} />}
        label="This is my own voice, and I consent to it being used to generate speech for this twin."
      />

      <Box>
        <Button variant="contained" disabled={!clip || !consent || submitting} onClick={handleSubmit}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </Box>
    </Stack>
  );
}
