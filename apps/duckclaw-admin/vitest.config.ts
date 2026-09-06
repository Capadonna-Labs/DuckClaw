import path from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: [
      'src/lib/opsSubprocessEnv.test.ts',
      'src/lib/pollWriteTask.test.ts',
      'src/lib/ansiLog.test.ts',
      'src/lib/draftManifestYaml.test.ts',
      'src/lib/workerRoleTemplates.test.ts',
      'src/lib/suggestedSkillInstall.test.ts',
      'src/lib/integrationGaps.test.ts',
      'src/lib/mcpConnectorsList.test.ts',
      'src/lib/mcpConnectorPrimaryAction.test.ts',
      'src/lib/mcpConnectorHealth.test.ts',
      'src/lib/mcpPresetAuth.test.ts',
      'src/lib/onboardingChecklist.test.ts',
      'src/lib/tauriRuntime.test.ts',
      'src/lib/desktopEnvFile.test.ts',
      'src/lib/manifestQuickEdit.test.ts',
      'src/lib/savedLoginCredentials.test.ts',
      'src/lib/playgroundLastSelection.test.ts',
      'src/lib/playgroundWorkerGate.test.ts',
      'src/components/chat/useAdminChatLoopPolling.test.ts',
      'src/components/chat/chatSuggestionsGating.test.ts',
      'src/components/chat/chatMarkdownMermaid.test.ts',
      'src/components/chat/chatMarkdown.test.ts',
      'src/lib/toolUsageGroup.test.ts',
      'src/lib/chatEphemeralMerge.test.ts',
      'src/lib/chatEphemeralWipe.test.ts',
      'src/lib/sessionExpired.test.ts',
      'src/lib/integrationDocsUrls.test.ts',
      'src/lib/chatDocumentAttachments.test.ts',
      'src/lib/desktopLocalFiles.test.ts',
      'src/lib/adminErrors.test.ts',
      'src/components/reports/reportsPageView.test.ts',
      'src/lib/htmlDashboardUpload.test.ts',
    ],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
