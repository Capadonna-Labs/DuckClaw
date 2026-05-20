import assert from 'node:assert/strict';
import { colorizePlainLogLine, stripAnsi } from './ansiLogParse';

assert.equal(stripAnsi('\x1b[31merror\x1b[0m'), 'error');
assert.equal(colorizePlainLogLine('ERROR: boom').className, 'text-red-400');
assert.equal(colorizePlainLogLine('WARN: slow').className, 'text-amber-300');
assert.equal(colorizePlainLogLine('0|Gateway | info').className, 'text-emerald-300');

console.log('ansiLog.test.ts: ok');
