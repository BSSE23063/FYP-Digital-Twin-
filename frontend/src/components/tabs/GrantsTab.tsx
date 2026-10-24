import { useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSnackbar } from "notistack";
import { apiErrorMessage } from "../../api/client";
import { createGrant, listGrants, revokeGrant } from "../../api/endpoints";

export default function GrantsTab({ twinId }: { twinId: string }) {
  const queryClient = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();
  const [email, setEmail] = useState("");
  const [tier, setTier] = useState("friends");

  const grantsQuery = useQuery({ queryKey: ["grants", twinId], queryFn: () => listGrants(twinId) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["grants", twinId] });

  const grantMutation = useMutation({
    mutationFn: () => createGrant(twinId, email, tier),
    onSuccess: () => {
      invalidate();
      setEmail("");
      enqueueSnackbar(`Granted ${tier} access to ${email}`, { variant: "success" });
    },
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  const revokeMutation = useMutation({
    mutationFn: (visitorId: string) => revokeGrant(twinId, visitorId),
    onSuccess: invalidate,
    onError: (err) => enqueueSnackbar(apiErrorMessage(err), { variant: "error" }),
  });

  return (
    <Stack spacing={3} sx={{ maxWidth: 640 }}>
      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>
            Grant access to a specific person
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Visitor email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              fullWidth
            />
            <TextField select label="Tier" value={tier} onChange={(e) => setTier(e.target.value)} fullWidth>
              <MenuItem value="friends">Friends</MenuItem>
              <MenuItem value="private">Private</MenuItem>
            </TextField>
            <Box>
              <Button
                variant="contained"
                disabled={!email.trim() || grantMutation.isPending}
                onClick={() => grantMutation.mutate()}
              >
                {grantMutation.isPending ? "Granting…" : "Grant access"}
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Box>
        <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
          Current grants
        </Typography>
        {grantsQuery.data?.length === 0 && <Typography color="text.secondary">No grants yet.</Typography>}
        <Stack spacing={1}>
          {grantsQuery.data?.map((g) => (
            <Card key={g.id} variant="outlined">
              <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
                  <Stack sx={{ flexGrow: 1 }}>
                    <Typography fontWeight={500}>{g.visitor_email || g.visitor_id}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      granted {new Date(g.granted_at).toLocaleDateString()}
                    </Typography>
                  </Stack>
                  <Chip size="small" label={g.tier_name} color="info" />
                  <Chip
                    size="small"
                    label={g.revoked_at ? "revoked" : "active"}
                    color={g.revoked_at ? "default" : "success"}
                    variant={g.revoked_at ? "outlined" : "filled"}
                  />
                  {!g.revoked_at && g.visitor_id && (
                    <Button size="small" color="error" onClick={() => revokeMutation.mutate(g.visitor_id!)}>
                      Revoke
                    </Button>
                  )}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      </Box>
    </Stack>
  );
}
