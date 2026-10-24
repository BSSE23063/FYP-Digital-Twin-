import { useRef, useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Step,
  StepLabel,
  Stepper,
  Stack,
  TextField,
} from "@mui/material";
import AddPhotoAlternateIcon from "@mui/icons-material/AddPhotoAlternate";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useSnackbar } from "notistack";
import { apiErrorMessage } from "../api/client";
import { createTwin, uploadAvatar, uploadVoiceSample } from "../api/endpoints";
import VoiceSampleRecorder from "./VoiceSampleRecorder";

const STEPS = ["Profile", "Photo", "Voice"];

/** Twin creation, as a 3-step wizard instead of one form: a photo and a voice
 * sample are mandatory, not optional extras bolted on after the fact (session
 * 14) — a twin isn't "done" until it looks and sounds like the person it's
 * standing in for. The twin row itself is created at the end of step 1, so
 * steps 2/3 are plain uploads against a real twin_id and can be retried
 * individually without losing the profile fields. */
export default function CreateTwinWizard({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [bio, setBio] = useState("");
  const [persona, setPersona] = useState(
    "You are a helpful, honest assistant speaking as this person. Never invent facts that aren't in your knowledge or memory."
  );
  const [twinId, setTwinId] = useState<string | null>(null);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);

  const reset = () => {
    setStep(0);
    setName("");
    setDomain("");
    setBio("");
    setTwinId(null);
    setAvatarFile(null);
    setAvatarPreview(null);
  };

  const handleClose = () => {
    if (step > 0) return; // twin already exists once step > 0 — see finishLater below
    reset();
    onClose();
  };

  const finishLater = () => {
    // Escape hatch for a stuck mic/camera, not a way around the requirement:
    // the twin exists but stays incomplete until its Overview tab's avatar
    // button / voice section are filled in — nothing here marks it "done".
    const id = twinId;
    reset();
    onClose();
    if (id) navigate(`/twins/${id}`);
  };

  const createMutation = useMutation({
    mutationFn: () =>
      createTwin({ name, domain, bio: bio || undefined, persona_prompt: persona || undefined }),
    onSuccess: (twin) => {
      queryClient.invalidateQueries({ queryKey: ["twins"] });
      setTwinId(twin.id);
      setStep(1);
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const avatarMutation = useMutation({
    mutationFn: () => uploadAvatar(twinId as string, avatarFile as File),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["twins"] });
      setStep(2);
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const voiceMutation = useMutation({
    mutationFn: ({ file, filename, consent }: { file: Blob; filename: string; consent: boolean }) =>
      uploadVoiceSample(twinId as string, file, filename, consent),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["twins"] });
      queryClient.invalidateQueries({ queryKey: ["twin", twinId] });
      const id = twinId;
      reset();
      onClose();
      if (id) navigate(`/twins/${id}`);
      enqueueSnackbar("Twin created", { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Create a new twin</DialogTitle>
      <DialogContent>
        <Stepper activeStep={step} sx={{ mb: 3, mt: 1 }}>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        <AnimatePresence mode="wait" initial={false}>
        {step === 0 && (
          <Stack
            component={motion.div}
            key="step-0"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.2 }}
            spacing={2}>
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth autoFocus />
            <TextField
              label="Domain / expertise"
              placeholder="e.g. React & TypeScript development"
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
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              fullWidth
              multiline
              minRows={3}
            />
            <Stack direction="row" spacing={1.5} sx={{ justifyContent: "flex-end" }}>
              <Button onClick={handleClose}>Cancel</Button>
              <Button
                variant="contained"
                disabled={!name.trim() || !domain.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                {createMutation.isPending ? "Creating…" : "Next"}
              </Button>
            </Stack>
          </Stack>
        )}

        {step === 1 && (
          <Stack
            component={motion.div}
            key="step-1"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.2 }}
            spacing={2}
          >
            <Alert severity="info">A profile picture is required — visitors browse twins by face, not ID.</Alert>
            <Stack sx={{ alignItems: "center" }} spacing={2}>
              <Avatar
                src={avatarPreview || undefined}
                sx={{ width: 120, height: 120, bgcolor: "primary.light" }}
              >
                <SmartToyOutlinedIcon sx={{ fontSize: 56 }} />
              </Avatar>
              <Button
                variant="outlined"
                startIcon={<AddPhotoAlternateIcon />}
                onClick={() => fileInputRef.current?.click()}
              >
                {avatarFile ? "Choose a different photo" : "Choose a photo"}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  setAvatarFile(file);
                  setAvatarPreview(URL.createObjectURL(file));
                }}
              />
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ justifyContent: "space-between" }}>
              <Button onClick={finishLater} color="inherit">
                Finish later
              </Button>
              <Button
                variant="contained"
                disabled={!avatarFile || avatarMutation.isPending}
                onClick={() => avatarMutation.mutate()}
              >
                {avatarMutation.isPending ? "Uploading…" : "Next"}
              </Button>
            </Stack>
          </Stack>
        )}

        {step === 2 && (
          <Stack
            component={motion.div}
            key="step-2"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.2 }}
            spacing={2}
          >
            <Alert severity="info">
              A voice sample is required — this is what this twin will actually sound like.
            </Alert>
            <VoiceSampleRecorder
              submitting={voiceMutation.isPending}
              submitLabel="Create twin"
              onSubmit={(file, filename, consent) => voiceMutation.mutate({ file, filename, consent })}
            />
            <Stack direction="row" sx={{ justifyContent: "flex-start" }}>
              <Button onClick={finishLater} color="inherit">
                Finish later
              </Button>
            </Stack>
          </Stack>
        )}
        </AnimatePresence>
      </DialogContent>
    </Dialog>
  );
}
