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
          // In-between shades (50/200/400/600/800/950) are interpolated: ~770 class uses referenced
          // them while undefined, so they rendered nothing (e.g. white text on no background).
          blue: {
            950: '#001433',
            900: '#001E4E',   // Sidebar, cabeceras primarias
            800: '#002E7A',
            700: '#003DA5',   // Botones primarios, íconos activos
            600: '#004AAE',
            500: '#0057B8',   // Hover states, enlaces
            400: '#2574C9',
            300: '#4A90D9',   // Estados deshabilitados
            200: '#90BBE8',
            100: '#D6E6F7',   // Fondos de alertas info
            50: '#EBF3FB',
          },
          cyan: {
            400: '#00A3E0',   // Acentos digitales GovTech
            200: '#68C8EC',
            100: '#D0EEF9',   // Fondos sutiles
            50: '#EAF7FC',
          },
          gold: {
            500: '#D4A017',   // Detalles institucionales
            100: '#FDF3D0',   // Fondos dorados suaves
          },
          gray: {
            900: '#1A2332',   // Texto principal
            800: '#2B3747',
            700: '#3D4A5C',   // Texto secundario
            600: '#546276',
            500: '#6B7A90',   // Placeholders
            400: '#929EB0',
            300: '#B8C2D0',   // Bordes
            200: '#D0D7E1',
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
