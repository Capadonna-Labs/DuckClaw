/**
 * Pipecat WavMediaManager registra AudioWorklets vía blob: al evaluar el bundle.
 * CSP estricta (script-src sin blob:) bloquea addModule — redirigimos a /pipecat/*.worklet.js.
 */
const PIPECAT_JS_WORKLET_PATHS = [
  '/pipecat/stream-processor.worklet.js',
  '/pipecat/audio-processor.worklet.js',
] as const;

export function installPipecatWorkletUrlPatch(): () => void {
  if (typeof window === 'undefined' || typeof URL.createObjectURL !== 'function') {
    return () => {};
  }

  const nativeCreateObjectURL = URL.createObjectURL.bind(URL);
  let jsWorkletIndex = 0;

  URL.createObjectURL = ((blob: Blob) => {
    if (blob.type === 'application/javascript' && jsWorkletIndex < PIPECAT_JS_WORKLET_PATHS.length) {
      const staticPath = PIPECAT_JS_WORKLET_PATHS[jsWorkletIndex];
      jsWorkletIndex += 1;
      return new URL(staticPath, window.location.origin).href;
    }
    return nativeCreateObjectURL(blob);
  }) as typeof URL.createObjectURL;

  return () => {
    URL.createObjectURL = nativeCreateObjectURL;
  };
}
