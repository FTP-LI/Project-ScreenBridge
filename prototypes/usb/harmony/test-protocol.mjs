import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FrameDecoder, crc32 } from './entry/src/main/ets/protocol.ts';

const vector = Buffer.from('5342503107000000090000002639f4cb313233343536373839', 'hex');
test('CRC32 golden vector and fragmented/coalesced echo', () => {
  assert.equal(crc32(new TextEncoder().encode('123456789')), 0xCBF43926);
  const decoder = new FrameDecoder();
  decoder.push(vector.subarray(0, 3));
  assert.equal(decoder.take(), undefined);
  decoder.push(Buffer.concat([vector.subarray(3), vector]));
  assert.deepEqual(Buffer.from(decoder.take()), vector);
  assert.deepEqual(Buffer.from(decoder.take()), vector);
  assert.equal(decoder.take(), undefined);
});
test('reject corrupt magic, CRC and oversized length', () => {
  for (const index of [0, 8, 12]) {
    const bad = Buffer.from(vector);
    if (index === 8) bad.writeUInt32LE(65537, 8); else bad[index] ^= 1;
    const decoder = new FrameDecoder();
    decoder.push(bad);
    assert.throws(() => decoder.take());
  }
});
test('buffer remains bounded when caller does not drain', () => {
  assert.throws(() => new FrameDecoder().push(new Uint8Array(65536 + 16 + 16385)));
});
