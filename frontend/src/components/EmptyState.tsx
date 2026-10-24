import { Box, Button, Stack, Typography } from "@mui/material";
import type { SvgIconProps } from "@mui/material";
import type { ComponentType } from "react";

/** A consistent "nothing here yet" treatment — icon in a soft tinted circle,
 * a short message, and an optional single action. Used everywhere a list can
 * be empty instead of each page inventing its own one-line text. */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}: {
  icon: ComponentType<SvgIconProps>;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <Stack spacing={1.5} sx={{ alignItems: "center", textAlign: "center", py: 6, px: 2 }}>
      <Box
        sx={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          bgcolor: "#EEF2FF",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon sx={{ fontSize: 28, color: "primary.main" }} />
      </Box>
      <Typography variant="subtitle1" fontWeight={600}>
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 360 }}>
          {description}
        </Typography>
      )}
      {actionLabel && onAction && (
        <Button variant="contained" size="small" onClick={onAction} sx={{ mt: 1 }}>
          {actionLabel}
        </Button>
      )}
    </Stack>
  );
}
