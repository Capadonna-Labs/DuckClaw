/** @type {import('next').NextConfig} */
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isProd = process.env.ENV === 'production';
const isDesktopBuild = process.env.NEXT_PUBLIC_DUCKCLAW_DESKTOP === '1';

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  // microphone=(self) — notas de voz en el compositor del Asistente (getUserMedia)
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(self), geolocation=()' },
  ...(isProd
    ? [{ key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' }]
    : []),
];

const relaxBuild = process.env.DUCKCLAW_ADMIN_RELAX_BUILD === '1';

const nextConfig = {
  output: "standalone",
  transpilePackages: ['date-fns'],
  ...(relaxBuild
    ? {
        typescript: { ignoreBuildErrors: true },
        eslint: { ignoreDuringBuilds: true },
      }
    : {}),
  webpack(config) {
    if (!isDesktopBuild) {
      const stub = path.join(__dirname, 'src/lib/tauriStubs/empty.ts');
      config.resolve.alias = {
        ...config.resolve.alias,
        '@tauri-apps/plugin-updater': stub,
        '@tauri-apps/plugin-process': stub,
        '@tauri-apps/api/core': stub,
      };
    }
    return config;
  },
  async headers() {
    return [
      {
        source: '/api/admin/reports/:reportId',
        headers: [
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
        ],
      },
      { source: '/(.*)', headers: securityHeaders },
    ];
  },
};

export default nextConfig;
