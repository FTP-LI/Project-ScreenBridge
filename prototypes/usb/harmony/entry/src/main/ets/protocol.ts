export const MAX_PAYLOAD: number = 65536;

export function crc32(bytes: Uint8Array): number {
  let crc: number = 0xFFFFFFFF;
  for (let i: number = 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let bit: number = 0; bit < 8; bit++) {
      crc = (crc >>> 1) ^ ((crc & 1) !== 0 ? 0xEDB88320 : 0);
    }
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

// Retain incomplete frames across USB reads; reject before allocating from an untrusted length.
export class FrameDecoder {
  private pending: Uint8Array = new Uint8Array(0);

  push(chunk: Uint8Array): void {
    if (this.pending.length + chunk.length > MAX_PAYLOAD + 16 + 16384) {
      throw new Error('Receive buffer limit exceeded');
    }
    const next: Uint8Array = new Uint8Array(this.pending.length + chunk.length);
    next.set(this.pending);
    next.set(chunk, this.pending.length);
    this.pending = next;
  }

  take(): ArrayBuffer | undefined {
    if (this.pending.length < 16) { return undefined; }
    if (this.pending[0] !== 83 || this.pending[1] !== 66 || this.pending[2] !== 80 || this.pending[3] !== 49) {
      throw new Error('Invalid SBP1 magic');
    }
    const header: DataView = new DataView(this.pending.buffer);
    const length: number = header.getUint32(8, true);
    if (length > MAX_PAYLOAD) { throw new Error('Payload exceeds 65536 bytes'); }
    if (this.pending.length < length + 16) { return undefined; }
    const frame: Uint8Array = this.pending.slice(0, length + 16);
    if (crc32(frame.subarray(16)) !== header.getUint32(12, true)) {
      throw new Error('CRC32 mismatch');
    }
    this.pending = this.pending.slice(length + 16);
    return frame.buffer;
  }
}

export interface VideoPicture {
  kind: string;
  accessUnit: number;
  timestampUs: number;
  keyframe: boolean;
  payload: Uint8Array;
}

const VIDEO_HEADER: number = 22;
const MAX_FRAGMENTS: number = 256;

// Reassemble one SBV1 access unit. A newer unit replaces an unfinished one,
// and a delta is kept only after a keyframe has been delivered.
export class VideoAssembler {
  dropped: number = 0;
  discarded: number = 0;
  private readonly maxBytes: number;
  private synced: boolean = false;
  private unit: number = -1;
  private count: number = 0;
  private flags: number = 0;
  private timestamp: number = 0;
  private parts: Array<Uint8Array | undefined> = [];
  private stored: number = 0;

  constructor(maxBytes: number) {
    if (maxBytes < 1) { throw new Error('invalid assembly limit'); }
    this.maxBytes = maxBytes;
  }

  retained(): number {
    return this.stored;
  }

  push(packet: Uint8Array): VideoPicture | undefined {
    if (packet.byteLength < VIDEO_HEADER) { throw new Error('short video packet'); }
    const view: DataView = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
    if (view.getUint8(0) !== 83 || view.getUint8(1) !== 66 || view.getUint8(2) !== 86 || view.getUint8(3) !== 49) {
      throw new Error('invalid video magic');
    }
    const kind: number = view.getUint8(4);
    const flags: number = view.getUint8(5);
    const accessUnit: number = view.getUint32(6, true);
    const timestampUs: number = view.getUint32(10, true) + view.getUint32(14, true) * 0x100000000;
    const index: number = view.getUint16(18, true);
    const count: number = view.getUint16(20, true);
    if (kind !== 1 && kind !== 2 && kind !== 3) { throw new Error('unknown video message'); }
    if (flags > 1 || count < 1 || count > MAX_FRAGMENTS || index >= count) {
      throw new Error('invalid video packet');
    }
    const payload: Uint8Array = packet.subarray(VIDEO_HEADER);
    if (payload.byteLength > MAX_PAYLOAD - VIDEO_HEADER) { throw new Error('fragment exceeds SBP1 payload'); }
    if (kind !== 2) {
      return {
        kind: kind === 1 ? 'capability' : 'stop',
        accessUnit: accessUnit,
        timestampUs: timestampUs,
        keyframe: false,
        payload: payload
      };
    }
    if (this.unit !== accessUnit) {
      if (this.unit !== -1) {
        this.dropped++;
        this.synced = false;
      }
      this.unit = accessUnit;
      this.count = count;
      this.flags = flags;
      this.timestamp = timestampUs;
      this.parts = new Array<Uint8Array | undefined>(count);
      this.stored = 0;
    }
    if (count !== this.count || flags !== this.flags || timestampUs !== this.timestamp) {
      this.lose();
      throw new Error('fragment metadata mismatch');
    }
    const previous: Uint8Array | undefined = this.parts[index];
    if (previous !== undefined && !sameBytes(previous, payload)) {
      this.lose();
      throw new Error('conflicting fragment');
    }
    if (previous === undefined && this.stored + payload.byteLength > this.maxBytes) {
      this.lose();
      throw new Error('access unit exceeds assembly limit');
    }
    if (previous === undefined) {
      this.parts[index] = payload.slice();
      this.stored += payload.byteLength;
    }
    let filled: number = 0;
    for (let i: number = 0; i < this.count; i++) {
      if (this.parts[i] !== undefined) { filled++; }
    }
    if (filled !== this.count) { return undefined; }
    const assembled: Uint8Array = new Uint8Array(this.stored);
    let offset: number = 0;
    for (let i: number = 0; i < this.count; i++) {
      const part: Uint8Array | undefined = this.parts[i];
      if (part === undefined) { throw new Error('missing fragment'); }
      assembled.set(part, offset);
      offset += part.byteLength;
    }
    const keyframe: boolean = (flags & 1) !== 0;
    const wasSynced: boolean = this.synced;
    this.clear();
    if (!keyframe && !wasSynced) {
      this.discarded++;
      return undefined;
    }
    if (keyframe) { this.synced = true; }
    return {
      kind: 'frame',
      accessUnit: accessUnit,
      timestampUs: timestampUs,
      keyframe: keyframe,
      payload: assembled
    };
  }

  private lose(): void {
    this.synced = false;
    this.clear();
  }

  private clear(): void {
    this.unit = -1;
    this.count = 0;
    this.flags = 0;
    this.timestamp = 0;
    this.parts = [];
    this.stored = 0;
  }
}

export function noteVideo(assembler: VideoAssembler, frame: Uint8Array): boolean {
  if (frame.byteLength < 20) { return false; }
  if (frame[16] !== 83 || frame[17] !== 66 || frame[18] !== 86 || frame[19] !== 49) { return false; }
  const picture: VideoPicture | undefined = assembler.push(frame.subarray(16));
  return picture !== undefined && picture.kind === 'frame' && picture.keyframe;
}

function sameBytes(left: Uint8Array, right: Uint8Array): boolean {
  if (left.byteLength !== right.byteLength) { return false; }
  for (let i: number = 0; i < left.byteLength; i++) {
    if (left[i] !== right[i]) { return false; }
  }
  return true;
}
