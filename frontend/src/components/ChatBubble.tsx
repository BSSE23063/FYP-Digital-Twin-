import { Avatar, Box, Paper, Stack, Typography } from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlineOutlined";
import { motion } from "framer-motion";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  audioBase64?: string;
  meta?: string;
}

export default function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <Stack
      component={motion.div}
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      direction="row"
      spacing={1.5}
      sx={{ justifyContent: isUser ? "flex-end" : "flex-start" }}
    >
      {!isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: "primary.light" }}>
          <SmartToyOutlinedIcon fontSize="small" />
        </Avatar>
      )}
      <Box sx={{ maxWidth: "75%" }}>
        <Paper
          elevation={0}
          sx={{
            px: 2,
            py: 1.2,
            bgcolor: isUser ? "primary.main" : "grey.100",
            color: isUser ? "primary.contrastText" : "text.primary",
            borderRadius: 3,
            borderTopRightRadius: isUser ? 4 : 24,
            borderTopLeftRadius: isUser ? 24 : 4,
          }}
        >
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
            {message.text}
          </Typography>
          {message.audioBase64 && (
            <Box sx={{ mt: 1 }}>
              <audio controls src={`data:audio/wav;base64,${message.audioBase64}`} style={{ height: 32, width: 220 }} />
            </Box>
          )}
        </Paper>
        {message.meta && (
          <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>
            {message.meta}
          </Typography>
        )}
      </Box>
      {isUser && (
        <Avatar sx={{ width: 32, height: 32, bgcolor: "secondary.light" }}>
          <PersonOutlineIcon fontSize="small" />
        </Avatar>
      )}
    </Stack>
  );
}
