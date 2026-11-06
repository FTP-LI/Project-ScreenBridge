import assert from 'node:assert/strict';
import { test } from 'node:test';
import { FrameDecoder, VideoAssembler, crc32, noteVideo } from './entry/src/main/ets/protocol.ts';

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

function videoPacket(kind, flags, accessUnit, timestampUs, index, count, payload) {
  const body = Buffer.from(payload);
  const packet = Buffer.alloc(22 + body.length);
  packet.write('SBV1', 0, 'ascii');
  packet.writeUInt8(kind, 4);
  packet.writeUInt8(flags, 5);
  packet.writeUInt32LE(accessUnit, 6);
  packet.writeUInt32LE(timestampUs >>> 0, 10);
  packet.writeUInt32LE(Math.floor(timestampUs / 0x100000000), 14);
  packet.writeUInt16LE(index, 18);
  packet.writeUInt16LE(count, 20);
  body.copy(packet, 22);
  return packet;
}

test('video fragments reassemble and deltas wait for a keyframe', () => {
  const assembler = new VideoAssembler(64);
  assert.equal(assembler.push(videoPacket(2, 0, 1, 5, 0, 1, 'delta')), undefined);
  assert.equal(assembler.discarded, 1);
  const key = assembler.push(videoPacket(2, 1, 2, 6, 0, 1, 'key'));
  assert.equal(Buffer.from(key.payload).toString(), 'key');
  assert.equal(key.keyframe, true);
  assert.equal(assembler.push(videoPacket(2, 0, 3, 7, 0, 2, 'ab')), undefined);
  assert.equal(assembler.push(videoPacket(2, 0, 4, 8, 0, 1, 'next')), undefined);
  assert.equal(assembler.dropped, 1);
  assert.equal(assembler.discarded, 2);
  const recovered = assembler.push(videoPacket(2, 1, 5, 9, 0, 1, 'new'));
  assert.equal(Buffer.from(recovered.payload).toString(), 'new');
  const capability = assembler.push(videoPacket(1, 0, 6, 0, 0, 1, 'h264'));
  assert.equal(capability.kind, 'capability');
  assert.equal(assembler.retained(), 0);
});

test('SBP1 payload carrying SBV1 counts only a keyframe', () => {
  const video = videoPacket(2, 1, 8, 10, 0, 1, 'pic');
  const frame = Buffer.alloc(16 + video.length);
  frame.write('SBP1', 0, 'ascii');
  frame.writeUInt32LE(3, 4);
  frame.writeUInt32LE(video.length, 8);
  frame.writeUInt32LE(crc32(video), 12);
  video.copy(frame, 16);
  const decoder = new FrameDecoder();
  decoder.push(frame);
  const taken = new Uint8Array(decoder.take());
  const assembler = new VideoAssembler(64);
  assert.equal(noteVideo(assembler, taken), true);
  assert.equal(noteVideo(assembler, taken), true);
  const echo = Buffer.alloc(16 + 4);
  echo.write('SBP1', 0, 'ascii');
  echo.writeUInt32LE(4, 8);
  echo.write('echo', 16, 'ascii');
  echo.writeUInt32LE(crc32(echo.subarray(16)), 12);
  const echoDecoder = new FrameDecoder();
  echoDecoder.push(echo);
  assert.equal(noteVideo(assembler, new Uint8Array(echoDecoder.take())), false);
});

test('tablet assembler accepts the host packet bytes', () => {
  const key = Buffer.from('534256310201020000000600000000000000000001006b6579', 'hex');
  const capability = Buffer.from('53425631010006000000000000000000000000000100800738043c', 'hex');
  const assembler = new VideoAssembler(64);
  const picture = assembler.push(key);
  assert.equal(Buffer.from(picture.payload).toString(), 'key');
  assert.equal(picture.keyframe, true);
  assert.equal(picture.accessUnit, 2);
  assert.equal(picture.timestampUs, 6);
  const described = assembler.push(capability);
  assert.equal(described.kind, 'capability');
  assert.equal(described.payload[0], 0x80);
  assert.equal(described.payload[1], 0x07);
  assert.equal(described.payload[2], 0x38);
  assert.equal(described.payload[3], 0x04);
  assert.equal(described.payload[4], 60);
});
