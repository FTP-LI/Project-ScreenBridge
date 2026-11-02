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
