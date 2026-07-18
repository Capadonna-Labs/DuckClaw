import { accessApi } from './admin/accessApi';
import { chatApi } from './admin/chatApi';
import { duckdbApi } from './admin/duckdbApi';
import { knowledgeApi } from './admin/knowledgeApi';
import { mcpApi } from './admin/mcpApi';
import { opsApi } from './admin/opsApi';
import { platformApi } from './admin/platformApi';
import { policiesApi } from './admin/policiesApi';
import { reportsApi } from './admin/reportsApi';
import { runtimeApi } from './admin/runtimeApi';
import { sandboxApi } from './admin/sandboxApi';
import { skillsApi } from './admin/skillsApi';
import { templatesApi } from './admin/templatesApi';
import { trainApi } from './admin/trainApi';
import { workspaceApi } from './admin/workspaceApi';

export type { TemplateSummary, TemplateDetail } from '@/types/admin';
export type {
  AdminConversation,
  PlaygroundVaultInfo,
} from './admin/chatApi';
export type {
  TrainPipelineResult,
  TrainStatus,
  TrainTraceFile,
} from './admin/trainApi';
export type {
  SandboxArtifactMeta,
  SandboxArtifactPreviewPayload,
  SandboxRunDetail,
  SandboxRunSummary,
} from './admin/sandboxApi';
export type {
  KnowledgeBrowseEntry,
  KnowledgeBrowseResponse,
  KnowledgeSearchResult,
  KnowledgeSource,
} from './admin/knowledgeApi';
export type {
  ProductivityArtifact,
  ReportInstanceDetail,
  ReportInstanceProgress,
  ReportInstanceSummary,
  ReportSectionProgress,
  ReportTemplateSummary,
} from './admin/reportsApi';
export type {
  AuditEntry,
} from './admin/platformApi';
export type {
  PromptPolicy,
  PromptPolicyRequirement,
  PromptPolicyHealth,
  PromptPolicyUpsertInput,
} from './admin/policiesApi';
export type {
  UserAgentDraft,
  WorkerCapabilities,
  IntegrationGapPayload,
  WorkerMcpGrantRow,
  WorkerMcpGrantsPayload,
} from './admin/templatesApi';
export type {
  DuckdbTableCatalog,
  DuckdbLegacySchema,
  DuckdbLegacyMainTable,
  DuckdbLegacySchemasResponse,
  DuckdbQueryResult,
  PgqGraphNode,
  PgqGraphLink,
  PgqGraphResult,
  VectorMemoryHit,
  VectorSearchResult,
  CodeDecisionRow,
} from './admin/duckdbApi';
export type {
  SkillCatalogItem,
  SkillCategorySkillItem,
  SkillCategoryPayload,
  SkillCategoriesCatalogResponse,
  IntegrationCatalogItem,
  IntegrationCatalogGroup,
  IntegrationCatalogResponse,
  CreateSkillInput,
  IndustryOption,
} from './admin/skillsApi';
export type {
  McpConnectorSummary,
  McpConnectorPreset,
  McpConnectorTestResult,
  McpToolInfo,
} from './admin/mcpApi';
export type {
  OpsCommand,
} from './admin/opsApi';
export type {
  ManagedWorkspaceDraft,
  WorkspaceProjectSummary,
  WorkspaceProjectsQuery,
  WorkspaceProjectsPage,
} from './admin/workspaceApi';

export const adminService = {
  ...platformApi,
  ...policiesApi,
  ...templatesApi,
  ...accessApi,
  ...runtimeApi,
  ...duckdbApi,
  ...skillsApi,
  ...mcpApi,
  ...opsApi,
  ...workspaceApi,
  ...chatApi,
  ...trainApi,
  ...sandboxApi,
  ...knowledgeApi,
  ...reportsApi,
};
