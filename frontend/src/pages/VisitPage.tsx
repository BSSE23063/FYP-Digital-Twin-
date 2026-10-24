import { useState } from "react";
import { Alert, Avatar, Box, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import { useNavigate } from "react-router-dom";
import { getTwin, getTwinBySlug } from "../api/endpoints";
import { apiErrorMessage } from "../api/client";

export default function VisitPage() {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setError(null);
    setLoading(true);
    try {
      let twin;
      try {
        twin = await getTwinBySlug(q);
      } catch {
        twin = await getTwin(q);
      }
      navigate(`/twins/${twin.id}/chat`);
    } catch {
      setError(`Couldn't find a twin for "${q}" — check the handle with its owner.`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
      <Card sx={{ maxWidth: 460, width: "100%" }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={2} sx={{ mb: 2, alignItems: "center" }}>
            <Avatar sx={{ bgcolor: "secondary.main", width: 48, height: 48 }}>
              <SearchIcon />
            </Avatar>
            <Typography variant="h5">Find a twin</Typography>
            <Typography variant="body2" color="text.secondary" align="center">
              Enter the handle its owner shared with you.
            </Typography>
          </Stack>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Stack spacing={2}>
            <TextField
              label="Twin handle"
              placeholder="e.g. umair-ai-twin"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              fullWidth
              autoFocus
            />
            <Button variant="contained" size="large" disabled={!query.trim() || loading} onClick={handleSearch}>
              {loading ? "Searching…" : "Start chatting"}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
