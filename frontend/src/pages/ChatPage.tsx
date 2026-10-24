import { useEffect, useRef, useState } from "react";
import {
  Avatar,
  Box,
  Button,
  Card,
  Chip,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import MicIcon from "@mui/icons-material/Mic";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import CallIcon from "@mui/icons-material/Call";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useSnackbar } from "notistack";
import { API_BASE, apiErrorMessage } from "../api/client";
import { getTwin, sendChatStream, sendVoiceChat } from "../api/endpoints";
import { useAuth } from "../context/useAuth";
import { usePushToTalk } from "../hooks/usePushToTalk";
import { useVoiceCall } from "../hooks/useVoiceCall";
import ChatBubble, { type ChatMessage } from "../components/ChatBubble";
import CallOverlay from "../components/CallOverlay";

export default function ChatPage() {
  const { twinId } = useParams<{ twinId: string }>();
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const { role, isAuthenticated } = useAuth();

  const twinQuery = useQuery({
    queryKey: ["twin", twinId],
    queryFn: () => getTwin(twinId!),
    enabled: Boolean(twinId),
  });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [inCall, setInCall] = useState(false);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, inCall]);

  const appendMessage = (msg: ChatMessage) => setMessages((m) => [...m, msg]);

  const handleSendText = async () => {
    const text = input.trim();
    if (!text || !twinId) return;
    setInput("");
    appendMessage({ id: crypto.randomUUID(), role: "user", text });
    setSending(true);

    // Streamed instead of waiting for the full answer: an empty bubble is
    // added up front and its text grows as chunks arrive, so the reply
    // appears live instead of popping in all at once after a multi-second wait.
    const assistantId = crypto.randomUUID();
    appendMessage({ id: assistantId, role: "assistant", text: "" });
    const updateAssistant = (patch: Partial<ChatMessage>) =>
      setMessages((m) => m.map((msg) => (msg.id === assistantId ? { ...msg, ...patch } : msg)));

    try {
      let accumulated = "";
      const result = await sendChatStream(twinId, text, conversationIdRef.current, (chunk) => {
        accumulated += chunk;
        updateAssistant({ text: accumulated });
      });
      conversationIdRef.current = result.conversation_id;
      updateAssistant({ meta: `${result.latency_ms}ms · ${result.sources.length} source(s)` });
    } catch (err) {
      setMessages((m) => m.filter((msg) => msg.id !== assistantId));
      enqueueSnackbar(apiErrorMessage(err), { variant: "error" });
    } finally {
      setSending(false);
    }
  };

  const pushToTalk = usePushToTalk((msg) => enqueueSnackbar(msg, { variant: "error" }));

  const handlePushToTalkStop = async () => {
    if (!twinId) return;
    const blob = await pushToTalk.stop();
    if (!blob) return;
    appendMessage({ id: crypto.randomUUID(), role: "user", text: "🎤 (voice message)" });
    setSending(true);
    try {
      const res = await sendVoiceChat(twinId, blob, conversationIdRef.current);
      conversationIdRef.current = res.conversation_id;
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { ...copy[copy.length - 1], text: res.question_text || "🎤 (voice message)" };
        return copy;
      });
      appendMessage({
        id: crypto.randomUUID(),
        role: "assistant",
        text: res.answer,
        audioBase64: res.audio_base64,
        meta: `${res.timing_ms.total}ms total`,
      });
    } catch (err) {
      enqueueSnackbar(apiErrorMessage(err), { variant: "error" });
    } finally {
      setSending(false);
    }
  };

  const voiceCall = useVoiceCall({
    onUtterance: async (blob) => {
      if (!twinId) throw new Error("No twin");
      appendMessage({ id: crypto.randomUUID(), role: "user", text: "🎤 (call)" });
      const res = await sendVoiceChat(twinId, blob, conversationIdRef.current);
      conversationIdRef.current = res.conversation_id;
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { ...copy[copy.length - 1], text: res.question_text || "🎤 (call)" };
        return copy;
      });
      appendMessage({ id: crypto.randomUUID(), role: "assistant", text: res.answer });
      return res.audio_base64;
    },
    onError: (message) => enqueueSnackbar(message, { variant: "error" }),
  });

  const startCall = async () => {
    setInCall(true);
    await voiceCall.startCall();
  };
  const endCall = () => {
    voiceCall.endCall();
    setInCall(false);
  };

  if (!twinId || twinQuery.isLoading) return <Typography color="text.secondary">Loading…</Typography>;
  if (!twinQuery.data) return <Typography color="error">Twin not found.</Typography>;
  const twin = twinQuery.data;
  const canManage = isAuthenticated && role === "owner" && twin.owner_id;

  return (
    <Box sx={{ maxWidth: 760, mx: "auto" }}>
      <Stack direction="row" spacing={1.5} sx={{ mb: 2, alignItems: "center" }}>
        <IconButton onClick={() => navigate(canManage ? `/twins/${twin.id}` : "/")}>
          <ArrowBackIcon />
        </IconButton>
        <Avatar
          src={twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined}
          sx={{ bgcolor: "primary.light" }}
        >
          <SmartToyOutlinedIcon fontSize="small" />
        </Avatar>
        <Stack sx={{ flexGrow: 1 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Typography variant="subtitle1" fontWeight={600}>
              {twin.name}
            </Typography>
            <Chip size="small" label={twin.domain} variant="outlined" color="primary" />
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {isAuthenticated && role === "owner" ? "You have full access to your own twin" : "Chatting as a visitor"}
          </Typography>
        </Stack>
        {!inCall && (
          <Button variant="contained" startIcon={<CallIcon />} onClick={startCall}>
            Start call
          </Button>
        )}
      </Stack>

      <Card sx={{ p: 0, overflow: "hidden" }}>
        {inCall ? (
          <CallOverlay
            twinName={twin.name}
            avatarUrl={twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined}
            status={voiceCall.status}
            volume={voiceCall.volume}
            onEnd={endCall}
          />
        ) : (
          <>
            <Box ref={scrollRef} sx={{ height: 440, overflowY: "auto", p: 2.5 }}>
              {messages.length === 0 && (
                <Stack spacing={1} sx={{ height: "100%", alignItems: "center", justifyContent: "center" }}>
                  <Typography color="text.secondary">
                    Say hello, or press "Start call" to talk hands-free.
                  </Typography>
                </Stack>
              )}
              <Stack spacing={1.5}>
                {messages.map((m) => (
                  <ChatBubble key={m.id} message={m} />
                ))}
                {sending && (
                  <Typography variant="caption" color="text.secondary" sx={{ pl: 6 }}>
                    Thinking…
                  </Typography>
                )}
              </Stack>
            </Box>

            <Box sx={{ borderTop: 1, borderColor: "divider", p: 1.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <TextField
                  placeholder="Say something…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendText())}
                  fullWidth
                  disabled={sending || pushToTalk.isRecording}
                  size="medium"
                />
                <Tooltip title={pushToTalk.isRecording ? "Stop and send" : "Record a voice message"}>
                  <IconButton
                    color={pushToTalk.isRecording ? "error" : "default"}
                    onClick={pushToTalk.isRecording ? handlePushToTalkStop : pushToTalk.start}
                    disabled={sending}
                  >
                    {pushToTalk.isRecording ? <StopCircleIcon /> : <MicIcon />}
                  </IconButton>
                </Tooltip>
                <IconButton color="primary" onClick={handleSendText} disabled={!input.trim() || sending}>
                  <SendIcon />
                </IconButton>
              </Stack>
            </Box>
          </>
        )}
      </Card>
    </Box>
  );
}
