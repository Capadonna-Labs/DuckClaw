/** Gateway managed by systemd instead of PM2 when DUCKCLAW_GATEWAY_SYSTEMD_UNIT is set. */

export function gatewaySystemdUnit(): string | null {
  const unit = (process.env.DUCKCLAW_GATEWAY_SYSTEMD_UNIT || '').trim();
  return unit || null;
}

export function gatewayManagedBySystemd(): boolean {
  return gatewaySystemdUnit() !== null;
}
