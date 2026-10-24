import { Avatar, Card, CardActionArea, CardContent, Chip, Stack, Typography } from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { API_BASE } from "../api/client";
import type { Twin } from "../api/types";

export default function TwinCard({ twin, onClick }: { twin: Twin; onClick: () => void }) {
  return (
    <Card>
      <CardActionArea onClick={onClick}>
        <CardContent>
          <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
            <Avatar
              src={twin.avatar_url ? `${API_BASE}${twin.avatar_url}` : undefined}
              sx={{ width: 56, height: 56, bgcolor: "primary.light" }}
            >
              <SmartToyOutlinedIcon />
            </Avatar>
            <Stack spacing={0.4} sx={{ minWidth: 0 }}>
              <Typography variant="subtitle1" fontWeight={600} noWrap>
                {twin.name}
              </Typography>
              <Chip size="small" label={twin.domain} variant="outlined" color="primary" sx={{ alignSelf: "flex-start" }} />
            </Stack>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
