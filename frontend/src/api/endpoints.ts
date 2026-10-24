import { API_BASE, apiClient } from "./client";
import type {
  AuthResponse,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
  CuratedDraft,
  GapCluster,
  Grant,
  KnowledgeGap,
  QdrantCollectionSummary,
  QdrantPointsPage,
  Source,
  SourceRef,
  Twin,
  Visibility,
  VoiceChatResponse,
  VoiceNoteResponse,
} from "./types";

// ── auth ─────────────────────────────────────────────────────

export const registerOwner = (email: string, password: string, display_name: string) =>
  apiClient.post<AuthResponse>("/auth/register", { email, password, display_name }).then((r) => r.data);

export const loginOwner = (email: string, password: string) =>
  apiClient.post<AuthResponse>("/auth/login", { email, password }).then((r) => r.data);

export const loginVisitor = (email: string, display_name: string) =>
  apiClient.post<AuthResponse>("/auth/visitor-login", { email, display_name }).then((r) => r.data);

// ── twins ────────────────────────────────────────────────────

export const createTwin = (payload: { name: string; domain: string; bio?: string; persona_prompt?: string }) =>
  apiClient.post<Twin>("/twins", payload).then((r) => r.data);

export const listMyTwins = () => apiClient.get<Twin[]>("/twins").then((r) => r.data);

export const listPublicTwins = () => apiClient.get<Twin[]>("/twins/public").then((r) => r.data);

export const getTwin = (twinId: string) => apiClient.get<Twin>(`/twins/${twinId}`).then((r) => r.data);

export const getTwinBySlug = (slug: string) =>
  apiClient.get<Twin>(`/twins/by-slug/${slug}`).then((r) => r.data);

export const updateTwin = (
  twinId: string,
  payload: { name?: string; bio?: string; persona_prompt?: string; domain?: string }
) => apiClient.patch<Twin>(`/twins/${twinId}`, payload).then((r) => r.data);

export const uploadAvatar = (twinId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiClient.post<Twin>(`/twins/${twinId}/avatar`, form).then((r) => r.data);
};

export const uploadVoiceSample = (twinId: string, file: Blob, filename: string, consent: boolean) => {
  const form = new FormData();
  form.append("file", file, filename);
  form.append("consent", String(consent));
  return apiClient.post<Twin>(`/twins/${twinId}/voice-sample`, form).then((r) => r.data);
};

export const deleteTwin = (twinId: string) => apiClient.delete(`/twins/${twinId}`);

// ── sources (knowledge) ─────────────────────────────────────

export const listSources = (twinId: string) =>
  apiClient.get<Source[]>(`/twins/${twinId}/sources`).then((r) => r.data);

export const ingestText = (twinId: string, name: string, text: string, visibility: Visibility) =>
  apiClient
    .post<Source>(`/twins/${twinId}/sources/text`, { name, text, visibility })
    .then((r) => r.data);

export const uploadSourceFile = (twinId: string, file: File, visibility: Visibility) => {
  const form = new FormData();
  form.append("file", file);
  form.append("visibility", visibility);
  return apiClient.post<Source>(`/twins/${twinId}/sources/upload`, form).then((r) => r.data);
};

export const ingestGithub = (twinId: string, username: string, visibility: Visibility) =>
  apiClient
    .post<Source>(`/twins/${twinId}/sources/github`, { username, visibility })
    .then((r) => r.data);

export const ingestVoiceNote = (twinId: string, audioBlob: Blob, visibility: Visibility) => {
  const form = new FormData();
  form.append("audio", audioBlob, "note.webm");
  form.append("visibility", visibility);
  return apiClient
    .post<VoiceNoteResponse>(`/twins/${twinId}/sources/voice-note`, form)
    .then((r) => r.data);
};

export const deleteSource = (twinId: string, sourceId: string) =>
  apiClient.delete(`/twins/${twinId}/sources/${sourceId}`);

// ── access grants ────────────────────────────────────────────

export const listGrants = (twinId: string) =>
  apiClient.get<Grant[]>(`/twins/${twinId}/grants`).then((r) => r.data);

export const createGrant = (twinId: string, visitor_email: string, tier_name: string) =>
  apiClient.post<Grant>(`/twins/${twinId}/grants`, { visitor_email, tier_name }).then((r) => r.data);

export const revokeGrant = (twinId: string, visitorId: string) =>
  apiClient.delete(`/twins/${twinId}/grants/${visitorId}`);

// ── knowledge gaps ───────────────────────────────────────────

export const listKnowledgeGaps = (twinId: string, status?: string) =>
  apiClient
    .get<KnowledgeGap[]>(`/twins/${twinId}/knowledge-gaps`, { params: status ? { status } : {} })
    .then((r) => r.data);

export const answerKnowledgeGap = (
  twinId: string,
  gapId: string,
  answer_text: string,
  visibility: Visibility
) =>
  apiClient
    .post<KnowledgeGap>(`/twins/${twinId}/knowledge-gaps/${gapId}/answer`, { answer_text, visibility })
    .then((r) => r.data);

export const dismissKnowledgeGap = (twinId: string, gapId: string) =>
  apiClient.post(`/twins/${twinId}/knowledge-gaps/${gapId}/dismiss`);

// ── knowledge gaps: multi-agent collection (Analyst + Curator) ─

export const analyzeKnowledgeGaps = (twinId: string) =>
  apiClient.get<GapCluster[]>(`/twins/${twinId}/knowledge-gaps/analyze`).then((r) => r.data);

export const curateGapAnswer = (twinId: string, gapIds: string[], rawAnswer: string) =>
  apiClient
    .post<CuratedDraft>(`/twins/${twinId}/knowledge-gaps/curate`, { gap_ids: gapIds, raw_answer: rawAnswer })
    .then((r) => r.data);

export const confirmGapCluster = (twinId: string, gapIds: string[], text: string, visibility: Visibility) =>
  apiClient
    .post<KnowledgeGap[]>(`/twins/${twinId}/knowledge-gaps/confirm`, { gap_ids: gapIds, text, visibility })
    .then((r) => r.data);

// ── conversations ────────────────────────────────────────────

export const listConversations = (twinId: string) =>
  apiClient.get<ConversationSummary[]>(`/twins/${twinId}/conversations`).then((r) => r.data);

export const getConversation = (twinId: string, conversationId: string) =>
  apiClient
    .get<ConversationDetail>(`/twins/${twinId}/conversations/${conversationId}`)
    .then((r) => r.data);

// ── chat + voice ─────────────────────────────────────────────

export const sendChat = (twinId: string, message: string, conversationId?: string | null) =>
  apiClient
    .post<ChatResponse>(`/twins/${twinId}/chat`, { message, conversation_id: conversationId ?? null })
    .then((r) => r.data);

export interface ChatStreamDone {
  conversation_id: string;
  sources: SourceRef[];
  latency_ms: number;
}

/** Reads the newline-delimited-JSON body from POST /chat/stream and calls
 * onChunk as each piece of the answer arrives, instead of waiting for the
 * full response like sendChat does. Uses fetch + a stream reader rather than
 * EventSource, since EventSource can't send a POST body (the message) at
 * all. Resolves with the same trailing metadata sendChat returns, minus
 * `answer` — the caller already has the full text from the accumulated
 * chunks by the time this resolves. */
export async function sendChatStream(
  twinId: string,
  message: string,
  conversationId: string | null | undefined,
  onChunk: (text: string) => void
): Promise<ChatStreamDone> {
  const authHeader = apiClient.defaults.headers.common["Authorization"] as string | undefined;
  const res = await fetch(`${API_BASE}/twins/${twinId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: ChatStreamDone | null = null;

  const handleLine = (line: string) => {
    if (!line.trim()) return;
    const evt = JSON.parse(line);
    if (evt.type === "chunk") onChunk(evt.text);
    else if (evt.type === "error") throw new Error(evt.detail || "Something went wrong");
    else if (evt.type === "done") done = evt;
  };

  while (true) {
    const { done: streamDone, value } = await reader.read();
    if (streamDone) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      handleLine(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 1);
    }
  }
  if (buffer.trim()) handleLine(buffer);

  if (!done) throw new Error("Stream ended without a result");
  return done;
}

export const sendVoiceChat = (twinId: string, audioBlob: Blob, conversationId?: string | null) => {
  const form = new FormData();
  form.append("audio", audioBlob, "utterance.webm");
  if (conversationId) form.append("conversation_id", conversationId);
  return apiClient
    .post<VoiceChatResponse>(`/twins/${twinId}/voice-chat`, form)
    .then((r) => r.data);
};

// ── Qdrant explorer (debug) ─────────────────────────────────

export const listQdrantCollections = () =>
  apiClient.get<QdrantCollectionSummary[]>("/debug/qdrant/twins").then((r) => r.data);

export const listTwinPoints = (
  twinId: string,
  params: { point_kind?: string; limit?: number; offset?: string }
) =>
  apiClient
    .get<QdrantPointsPage>(`/debug/qdrant/twins/${twinId}/points`, { params })
    .then((r) => r.data);
