import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CONTROL_MAGIC, CONTROL_VERSION, encodeControl, decodeControl } from '../../apps/harmony/screenbridge/entry/src/main/ets/protocol.ts';

test('formal tablet protocol encodes and decodes SBC1 ready', () => {
  const payload = encodeControl('ready', CONTROL_VERSION, true, true);
  assert.deepEqual(Array.from(payload), [83, 66, 67, 49, 2, 1, 0, 3]);
  assert.equal(new TextDecoder().decode(payload.subarray(0, 4)), CONTROL_MAGIC);
  assert.deepEqual(decodeControl(payload), {
    kind: 'ready', version: 1, paired: true, accept: true
  });
});

test('formal tablet protocol rejects malformed control flags', () => {
  const bad = encodeControl('stop', 1, false, false);
  bad[7] = 0x80;
  assert.throws(() => decodeControl(bad));
});
