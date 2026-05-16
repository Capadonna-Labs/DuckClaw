import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        dark: {
          bg:        '#0D1117',
          surface:   '#161B22',
          sidebar:   '#010409',
          border:    '#30363D',
          text:      '#E6EDF3',
          muted:     '#8B949E',
          accent:    '#1F6FEB',
          cyan:      '#58A6FF',
        },
        gov: {
          blue: {
            900: '#001E4E',   // Sidebar, cabeceras primarias
            700: '#003DA5',   // Botones primarios, íconos activos
            500: '#0057B8',   // Hover states, enlaces
            300: '#4A90D9',   // Estados deshabilitados
            100: '#D6E6F7',   // Fondos de alertas info
          },
          cyan: {
            400: '#00A3E0',   // Acentos digitales GovTech
            100: '#D0EEF9',   // Fondos sutiles
          },
          gold: {
            500: '#D4A017',   // Detalles institucionales
            100: '#FDF3D0',   // Fondos dorados suaves
          },
          gray: {
            900: '#1A2332',   // Texto principal
            700: '#3D4A5C',   // Texto secundario
            500: '#6B7A90',   // Placeholders
            300: '#B8C2D0',   // Bordes
            100: '#E8ECF2',   // Separadores
            50:  '#F4F6F9',   // Fondo general
          },
        },
        sem: {
          green:  '#00875A',   // Semáforo: seguro (> 10 días)
          yellow: '#D97706',   // Semáforo: atención (4–10 días)
          red:    '#DC2626',   // Semáforo: crítico (≤ 3 días)
          'green-bg':  '#ECFDF5',
          'yellow-bg': '#FFFBEB',
          'red-bg':    '#FEF2F2',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
      },
    },
  },
  plugins: [],
};
export default config;
