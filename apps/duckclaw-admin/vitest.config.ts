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
      'src/components/chat/useAdminChatLoopPolling.test.ts',
    ],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
