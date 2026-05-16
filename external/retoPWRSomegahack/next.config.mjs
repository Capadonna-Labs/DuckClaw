/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // DuckDB es nativo (node-pre-gyp); no empaquetar con webpack.
    serverComponentsExternalPackages: ['duckdb'],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals.push('duckdb');
    }
    return config;
  },
};

export default nextConfig;
