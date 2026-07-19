import { adminService } from '@/services/adminService';

export type PlaygroundConfig = Awaited<ReturnType<typeof adminService.getPlaygroundConfig>>;
export type PlaygroundSettingsModal = 'commands' | 'vault' | 'model' | 'instructions' | 'routing' | null;
