import { useMemo, useState } from "react";
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import StorageIcon from "@mui/icons-material/Storage";
import { useQuery } from "@tanstack/react-query";
import { listQdrantCollections, listTwinPoints } from "../api/endpoints";
import type { QdrantCollectionSummary, QdrantPoint } from "../api/types";

// Validated categorical palette (dataviz skill, references/palette.md) —
// slots 1 (blue) + 3 (aqua) clear the all-pairs CVD/contrast gates together,
// and aqua echoes this app's existing teal secondary color.
const KNOWLEDGE_COLOR = "#2a78d6";
const MEMORY_COLOR = "#1baf7a";
const TEXT_MUTED = "#898781";

const KIND_COLOR: Record<string, "default" | "info" | "secondary"> = {
  knowledge: "info",
  memory: "secondary",
};

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={600} sx={{ mt: 0.5 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

function TwinBarRow({
  twin,
  maxTotal,
  selected,
  onClick,
}: {
  twin: QdrantCollectionSummary;
  maxTotal: number;
  selected: boolean;
  onClick: () => void;
}) {
  const total = twin.total_points || 0;
  // The bar's own width represents this twin's share of the largest twin's
  // total (not a fraction of the grand total) — the comparison that matters
  // here is "which twin has the most content", so scale to the max, not 100%.
  const widthPct = maxTotal > 0 ? Math.max((total / maxTotal) * 100, total > 0 ? 3 : 0) : 0;
  const knowledgePct = total > 0 ? (twin.knowledge_points / total) * 100 : 0;
  const memoryPct = total > 0 ? (twin.memory_points / total) * 100 : 0;

  return (
    <Box
      onClick={onClick}
      sx={{
        p: 1.25,
        borderRadius: 2,
        cursor: "pointer",
        border: "1px solid",
        borderColor: selected ? "primary.main" : "transparent",
        bgcolor: selected ? "primary.light" : "transparent",
        "&:hover": { bgcolor: selected ? "primary.light" : "grey.100" },
      }}
    >
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline", mb: 0.5 }}>
        <Typography
          variant="body2"
          fontWeight={600}
          noWrap
          sx={{ color: selected ? "primary.contrastText" : "text.primary" }}
        >
          {twin.twin_name}
        </Typography>
        <Typography
          variant="caption"
          sx={{ color: selected ? "primary.contrastText" : "text.secondary", flexShrink: 0, ml: 1 }}
        >
          {total} point{total === 1 ? "" : "s"}
        </Typography>
      </Stack>
      {/* Stacked bar: knowledge + memory segments, 24px cap, 4px rounded
          data-end, 2px surface gap between segments (marks-and-anatomy.md) */}
      <Box sx={{ width: `${widthPct}%`, minWidth: total > 0 ? 24 : 0, height: 16, display: "flex", gap: "2px" }}>
        {knowledgePct > 0 && (
          <Box
            sx={{
              width: `${knowledgePct}%`,
              bgcolor: KNOWLEDGE_COLOR,
              borderRadius: memoryPct > 0 ? "4px 0 0 4px" : "4px",
            }}
          />
        )}
        {memoryPct > 0 && (
          <Box
            sx={{
              width: `${memoryPct}%`,
              bgcolor: MEMORY_COLOR,
              borderRadius: knowledgePct > 0 ? "0 4px 4px 0" : "4px",
            }}
          />
        )}
      </Box>
    </Box>
  );
}

function PointCard({ point }: { point: QdrantPoint }) {
  const { document, point_kind, visibility, source_id, chunk_index, visitor_id, ...rest } =
    point.payload as Record<string, unknown>;
  const extra = Object.entries(rest).filter(([k]) => !["char_start", "char_end"].includes(k));

  return (
    <Card variant="outlined">
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: "center", flexWrap: "wrap" }}>
          {typeof point_kind === "string" && (
            <Chip size="small" label={point_kind} color={KIND_COLOR[point_kind] || "default"} />
          )}
          {typeof visibility === "string" && <Chip size="small" variant="outlined" label={visibility} />}
          {typeof chunk_index === "number" && <Chip size="small" variant="outlined" label={`chunk ${chunk_index}`} />}
          {typeof visitor_id === "string" && (
            <Chip size="small" variant="outlined" label={`visitor ${visitor_id.slice(0, 8)}…`} />
          )}
          <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
            {point.id.slice(0, 8)}…
          </Typography>
        </Stack>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
          {typeof document === "string" ? document : "(no document field)"}
        </Typography>
        {typeof source_id === "string" && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            source_id: {source_id}
            {extra.length > 0 && " · " + extra.map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

export default function QdrantExplorerPage() {
  const [selectedTwinId, setSelectedTwinId] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [offsets, setOffsets] = useState<(string | undefined)[]>([undefined]);
  const [pageIndex, setPageIndex] = useState(0);

  const collectionsQuery = useQuery({ queryKey: ["qdrant", "collections"], queryFn: listQdrantCollections });

  const selectTwin = (twinId: string) => {
    setSelectedTwinId(twinId === selectedTwinId ? null : twinId);
    setKindFilter("");
    setSearch("");
    setOffsets([undefined]);
    setPageIndex(0);
  };

  const pointsQuery = useQuery({
    queryKey: ["qdrant", "points", selectedTwinId, kindFilter, offsets[pageIndex]],
    queryFn: () =>
      listTwinPoints(selectedTwinId as string, {
        point_kind: kindFilter || undefined,
        limit: 25,
        offset: offsets[pageIndex],
      }),
    enabled: Boolean(selectedTwinId),
  });

  const filteredPoints = useMemo(() => {
    const points = pointsQuery.data?.points || [];
    if (!search.trim()) return points;
    const needle = search.toLowerCase();
    return points.filter((p) => JSON.stringify(p.payload).toLowerCase().includes(needle));
  }, [pointsQuery.data, search]);

  const twins = collectionsQuery.data || [];
  const selected = twins.find((c) => c.twin_id === selectedTwinId);
  const maxTotal = Math.max(1, ...twins.map((t) => t.total_points));

  const totals = useMemo(
    () =>
      twins.reduce(
        (acc, t) => ({
          twinsWithData: acc.twinsWithData + (t.total_points > 0 ? 1 : 0),
          points: acc.points + t.total_points,
          knowledge: acc.knowledge + t.knowledge_points,
          memory: acc.memory + t.memory_points,
        }),
        { twinsWithData: 0, points: 0, knowledge: 0, memory: 0 }
      ),
    [twins]
  );

  const goNext = () => {
    const next = pointsQuery.data?.next_offset;
    if (!next) return;
    setOffsets((o) => [...o.slice(0, pageIndex + 1), next]);
    setPageIndex((i) => i + 1);
  };
  const goPrev = () => setPageIndex((i) => Math.max(0, i - 1));

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: "center" }}>
        <StorageIcon color="action" />
        <Typography variant="h5">Vector DB dashboard</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Every chunk actually indexed in Qdrant for your twins — what retrieval can see, not just what
        the Knowledge tab's source list shows.
      </Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatTile label="Twins with data" value={totals.twinsWithData} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatTile label="Total points indexed" value={totals.points} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatTile label="Knowledge chunks" value={totals.knowledge} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatTile label="Memory chunks" value={totals.memory} />
        </Grid>
      </Grid>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}>
            <Typography variant="subtitle1" fontWeight={600}>
              Points by twin
            </Typography>
            {/* Legend — always present for 2+ series (marks-and-anatomy.md) */}
            <Stack direction="row" spacing={2}>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: KNOWLEDGE_COLOR }} />
                <Typography variant="caption" color="text.secondary">
                  Knowledge
                </Typography>
              </Stack>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: MEMORY_COLOR }} />
                <Typography variant="caption" color="text.secondary">
                  Memory
                </Typography>
              </Stack>
            </Stack>
          </Stack>

          {collectionsQuery.isLoading && <CircularProgress size={20} />}
          {twins.length === 0 && !collectionsQuery.isLoading && (
            <Typography color="text.secondary">You don't own any twins yet.</Typography>
          )}

          <Stack spacing={0.5}>
            {twins.map((t) => (
              <TwinBarRow
                key={t.twin_id}
                twin={t}
                maxTotal={maxTotal}
                selected={t.twin_id === selectedTwinId}
                onClick={() => selectTwin(t.twin_id)}
              />
            ))}
          </Stack>
          <Typography variant="caption" sx={{ color: TEXT_MUTED, display: "block", mt: 1.5 }}>
            Click a twin to browse its chunks below.
          </Typography>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardContent>
            <Stack direction="row" spacing={2} sx={{ mb: 2, alignItems: "center", flexWrap: "wrap" }}>
              <Typography variant="subtitle1" fontWeight={600}>
                {selected.twin_name}
              </Typography>
              <Chip label={`knowledge: ${selected.knowledge_points}`} color="info" variant="outlined" size="small" />
              <Chip label={`memory: ${selected.memory_points}`} color="secondary" variant="outlined" size="small" />
              {selected.vector_size && (
                <Chip label={`${selected.vector_size}-dim vectors`} variant="outlined" size="small" />
              )}
              <Typography variant="caption" color="text.secondary">
                {selected.collection_name}
              </Typography>
            </Stack>

            <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
              <TextField
                select
                size="small"
                label="Kind"
                value={kindFilter}
                onChange={(e) => {
                  setKindFilter(e.target.value);
                  setOffsets([undefined]);
                  setPageIndex(0);
                }}
                sx={{ width: 160 }}
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="knowledge">Knowledge</MenuItem>
                <MenuItem value="memory">Memory</MenuItem>
              </TextField>
              <TextField
                size="small"
                label="Search this page"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                fullWidth
              />
            </Stack>

            {pointsQuery.isLoading && <CircularProgress size={20} />}
            {pointsQuery.data && filteredPoints.length === 0 && (
              <Typography color="text.secondary">No points on this page.</Typography>
            )}

            <Stack spacing={1}>
              {filteredPoints.map((p) => (
                <PointCard key={p.id} point={p} />
              ))}
            </Stack>

            <Divider sx={{ my: 2 }} />
            <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <Box
                component="button"
                onClick={goPrev}
                disabled={pageIndex === 0}
                sx={{
                  border: "none",
                  bgcolor: "transparent",
                  color: pageIndex === 0 ? "text.disabled" : "primary.main",
                  cursor: pageIndex === 0 ? "default" : "pointer",
                  fontWeight: 600,
                }}
              >
                ← Prev page
              </Box>
              <Typography variant="caption" color="text.secondary">
                page {pageIndex + 1}
              </Typography>
              <Box
                component="button"
                onClick={goNext}
                disabled={!pointsQuery.data?.next_offset}
                sx={{
                  border: "none",
                  bgcolor: "transparent",
                  color: pointsQuery.data?.next_offset ? "primary.main" : "text.disabled",
                  cursor: pointsQuery.data?.next_offset ? "pointer" : "default",
                  fontWeight: 600,
                }}
              >
                Next page →
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
