import { useRef, useState } from "react";
import { Box, Button, Grid, Link as MuiLink, Skeleton, Stack, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import StorageIcon from "@mui/icons-material/Storage";
import PersonSearchOutlinedIcon from "@mui/icons-material/PersonSearchOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { listMyTwins, listPublicTwins } from "../api/endpoints";
import TwinCard from "../components/TwinCard";
import TwinGalleryCard from "../components/TwinGalleryCard";
import CreateTwinWizard from "../components/CreateTwinWizard";
import EmptyState from "../components/EmptyState";
import LandingHero from "../components/LandingHero";

function CardSkeleton({ height = 96 }: { height?: number }) {
  return <Skeleton variant="rounded" height={height} sx={{ borderRadius: 4 }} />;
}

// Shared stagger variants for both card grids below — each grid's container
// is the motion parent (variants=gridContainer), each card wrapped in a
// motion.div with variants=gridItem inherits the stagger automatically.
const gridContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
};
const gridItem = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

export default function DashboardPage() {
  const { role, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const galleryRef = useRef<HTMLDivElement>(null);

  const isOwner = isAuthenticated && role === "owner";

  const twinsQuery = useQuery({
    queryKey: ["twins"],
    queryFn: listMyTwins,
    enabled: isOwner,
  });

  const publicTwinsQuery = useQuery({
    queryKey: ["twins", "public"],
    queryFn: listPublicTwins,
    enabled: !isOwner,
  });

  if (!isOwner) {
    return (
      <Box>
        <LandingHero onBrowse={() => galleryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })} />

        <Stack ref={galleryRef} spacing={0.5} sx={{ mb: 3, textAlign: "center", scrollMarginTop: 88 }}>
          <Typography variant="h5">Who do you want to talk to?</Typography>
          <Typography color="text.secondary">
            Pick a twin below to start chatting — no handle needed. Have one already?{" "}
            <MuiLink component="button" onClick={() => navigate("/visit")}>
              Enter its handle instead
            </MuiLink>
            .
          </Typography>
        </Stack>

        {publicTwinsQuery.isLoading && (
          <Grid container spacing={2.5}>
            {[0, 1, 2].map((i) => (
              <Grid key={i} size={{ xs: 12, sm: 6, md: 4 }}>
                <CardSkeleton height={280} />
              </Grid>
            ))}
          </Grid>
        )}
        {publicTwinsQuery.data && publicTwinsQuery.data.length === 0 && (
          <EmptyState
            icon={PersonSearchOutlinedIcon}
            title="No twins published yet"
            description="Once an owner creates one, it'll show up here for anyone to chat with."
          />
        )}

        <Grid
          container
          spacing={2.5}
          component={motion.div}
          initial="hidden"
          animate="show"
          variants={gridContainer}
        >
          {publicTwinsQuery.data?.map((twin) => (
            <Grid key={twin.id} size={{ xs: 12, sm: 6, md: 4 }} component={motion.div} variants={gridItem}>
              <TwinGalleryCard twin={twin} onClick={() => navigate(`/twins/${twin.id}/chat`)} />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" sx={{ mb: 3, justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h5">Your twins</Typography>
        <Stack direction="row" spacing={1.5}>
          <Button variant="outlined" startIcon={<StorageIcon />} onClick={() => navigate("/debug/qdrant")}>
            Explore vector DB
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            New twin
          </Button>
        </Stack>
      </Stack>

      {twinsQuery.isLoading && (
        <Grid container spacing={2}>
          {[0, 1, 2].map((i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, md: 4 }}>
              <CardSkeleton />
            </Grid>
          ))}
        </Grid>
      )}
      {twinsQuery.data && twinsQuery.data.length === 0 && (
        <EmptyState
          icon={SmartToyOutlinedIcon}
          title="You haven't created a twin yet"
          description="A twin is built from a photo, a voice sample, and whatever knowledge you give it."
          actionLabel="Create your first twin"
          onAction={() => setCreateOpen(true)}
        />
      )}

      <Grid container spacing={2} component={motion.div} initial="hidden" animate="show" variants={gridContainer}>
        {twinsQuery.data?.map((twin) => (
          <Grid key={twin.id} size={{ xs: 12, sm: 6, md: 4 }} component={motion.div} variants={gridItem}>
            <TwinCard twin={twin} onClick={() => navigate(`/twins/${twin.id}`)} />
          </Grid>
        ))}
      </Grid>

      <CreateTwinWizard open={createOpen} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
