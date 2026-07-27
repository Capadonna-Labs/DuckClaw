/** Web-build stub when Tauri packages are not installed. */

export async function check(): Promise<null> {
  return null;
}

export async function relaunch(): Promise<void> {}

export async function invoke(_cmd: string, _args?: unknown): Promise<unknown> {
  return undefined;
}
