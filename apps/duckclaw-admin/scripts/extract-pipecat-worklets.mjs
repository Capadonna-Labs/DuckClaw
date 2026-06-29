/** One-off: extract Pipecat WavMediaManager worklets to public/pipecat/*.worklet.js */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const bundle = fs.readFileSync(
  path.join(root, '../node_modules/@pipecat-ai/small-webrtc-transport/dist/index.module.js'),
  'utf8'
);

function extractBetween(marker, endMarker) {
  const start = bundle.indexOf(marker);
  if (start < 0) throw new Error(`marker not found: ${marker}`);
  const from = start + marker.length;
  const end = bundle.indexOf(endMarker, from);
  if (end < 0) throw new Error(`end not found for ${marker}`);
  return bundle.slice(from, end);
}

const stream = extractBetween(
  'const $29a8a70a9466b14f$export$50b76700e2b15e9 = `\n',
  '`;\nconst $29a8a70a9466b14f$var$script'
);
const audio = extractBetween(
  'const $8e1d1e6ff08f6fb5$var$AudioProcessorWorklet = `\n',
  '`;\nconst $8e1d1e6ff08f6fb5$var$script'
);

function unescapeWorkletSource(source) {
  // Bundle embeds worklets in a template literal; escapes must become real JS.
  return source.replace(/\\`/g, '`').replace(/\\\$\{/g, '${');
}

const outDir = path.join(root, '../public/pipecat');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(
  path.join(outDir, 'stream-processor.worklet.js'),
  unescapeWorkletSource(stream.trimStart())
);
fs.writeFileSync(
  path.join(outDir, 'audio-processor.worklet.js'),
  unescapeWorkletSource(audio.trimStart())
);
console.log('wrote', outDir);
