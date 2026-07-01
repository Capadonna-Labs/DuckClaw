import { PageShell } from '@/components/admin/PageShell';

export type EmbeddedViewProps = {
  /** Oculta PageShell y cabecera h1 cuando la vista vive dentro de un hub. */
  embedded?: boolean;
};

type ViewChromeProps = EmbeddedViewProps & {
  children: React.ReactNode;
  className?: string;
};

/** Envuelve la vista en PageShell solo en rutas standalone. */
export function ViewChrome({ embedded, children, className }: ViewChromeProps) {
  if (embedded) {
    return <div className={className}>{children}</div>;
  }
  return <PageShell className={className}>{children}</PageShell>;
}
