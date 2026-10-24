// Mirrors the Pydantic response/request models in backend/api/*.py.
// Kept as one file since the backend keeps its schemas small and flat too.

export interface AuthResponse {
  user_id: string;
  email: string;
  display_name: string;
  token: string;
}

export interface Twin {
  id: string;
  owner_id: string;
  slug: string;
  name: string;
  domain: string;
  bio: string | null;
  persona_prompt: string | null;
  avatar_url: string | null;
  has_voice_sample: boolean;
  is_active: boolean;
}

export interface Source {
  id: string;
  twin_id: string;
  source_type: string;
  name: string;
  visibility: Visibility;
  status: "pending" | "processing" | "completed" | "failed";
  chunk_count: number;
  error_message: string | null;
}

export type Visibility = "public" | "friends" | "private";

export interface Grant {
  id: string;
  twin_id: string;
  visitor_id: string | null;
  visitor_email: string | null;
  tier_name: string;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface KnowledgeGap {
  id: string;
  twin_id: string;
  conversation_id: string;
  question_text: string;
  status: "pending" | "answered" | "dismissed";
  answer_text: string | null;
  resulting_source_id: string | null;
}

export interface SourceRef {
  source_id: string | null;
  score: number | null;
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  sources: SourceRef[];
  latency_ms: number;
}

export interface VoiceChatResponse {
  conversation_id: string;
  question_text: string;
  answer: string;
  sources: SourceRef[];
  audio_base64: string;
  timing_ms: Record<string, number>;
}

export interface VoiceNoteResponse {
  source: Source;
  transcript: string;
}

export interface QdrantCollectionSummary {
  twin_id: string;
  twin_name: string;
  collection_name: string;
  exists: boolean;
  vector_size: number | null;
  knowledge_points: number;
  memory_points: number;
  total_points: number;
}

export interface QdrantPoint {
  id: string;
  payload: Record<string, unknown>;
}

export interface QdrantPointsPage {
  points: QdrantPoint[];
  next_offset: string | null;
}

export interface GapCluster {
  theme: string;
  gap_ids: string[];
  suggested_prompt: string;
}

export interface CuratedDraft {
  text: string;
  suggested_visibility: Visibility;
  reasoning: string;
}

export interface ConversationSummary {
  id: string;
  visitor_name: string;
  channel: string;
  access_tier: string;
  is_owner_session: boolean;
  message_count: number;
  last_message_preview: string | null;
  created_at: string;
}

export interface ConversationMessage {
  id: string;
  role: "visitor" | "twin" | "system";
  content: string;
  policy_decision: string | null;
  confidence_score: number | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}
