import { usbManager } from '@kit.BasicServicesKit';
import { fileIo } from '@kit.CoreFileKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { FrameDecoder, VideoAssembler, decodeControl, encodeControl, encodeFrame } from '../protocol';

@Entry
@Component
struct Index {
  @State status: string = '正在等待电脑建立屏桥';
  @State frames: number = 0;
  @State bytes: number = 0;
  @State pictures: number = 0;
  @State busy: boolean = false;
  private running: boolean = false;
  private handle: usbManager.USBAccessoryHandle | undefined = undefined;
  private sequence: number = 0;

  private stop(): void {
    this.running = false;
    const handle = this.handle;
    this.handle = undefined;
    if (handle !== undefined) {
      try { usbManager.closeAccessory(handle); }
      catch (e) { this.status = `关闭失败：${(e as BusinessError).code}`; }
    }
  }

  aboutToAppear(): void { this.connect(); }
  aboutToDisappear(): void { this.stop(); }

  private async waitForAccessory(): Promise<usbManager.USBAccessory> {
    const deadline = Date.now() + 60000;
    while (this.running && Date.now() < deadline) {
      try {
        const matches = usbManager.getAccessoryList().filter((item: usbManager.USBAccessory) =>
          item.manufacturer === 'ScreenBridge' && item.product === 'USBProbe');
        if (matches.length === 1) { return matches[0]; }
        this.status = matches.length === 0 ? '正在等待电脑建立配件通道' : `匹配到 ${matches.length} 个配件，无法确定目标`;
      } catch (e) {
        this.status = '正在等待电脑建立配件通道';
      }
      await new Promise<void>((resolve: () => void) => setTimeout(resolve, 500));
    }
    throw new Error('60 秒内没有等到配件通道');
  }

  private async writeFrame(handle: usbManager.USBAccessoryHandle, payload: Uint8Array): Promise<void> {
    const frame = encodeFrame(this.sequence, payload);
    this.sequence = (this.sequence + 1) >>> 0;
    let offset: number = 0;
    while (offset < frame.length && this.running) {
      const end = Math.min(frame.length, offset + 16384);
      const chunk: ArrayBuffer = frame.slice(offset, end).buffer as ArrayBuffer;
      const written = await fileIo.write(handle.accessoryFd, chunk);
      if (written <= 0 || written > end - offset) {
        throw new Error('USB 写入未前进或长度异常');
      }
      offset += written;
    }
  }

  private async connect(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    this.running = true;
    this.sequence = 0;
    this.frames = 0;
    this.bytes = 0;
    this.pictures = 0;
    try {
      const accessory = await this.waitForAccessory();
      if (!usbManager.hasAccessoryRight(accessory)) {
        this.status = '请允许 USB 配件访问';
        if (!await usbManager.requestAccessoryRight(accessory)) { throw new Error('USB 配件授权被拒绝'); }
      }
      if (!this.running) { return; }
      const handle = usbManager.openAccessory(accessory);
      this.handle = handle;
      this.status = '已打开配件，正在通知电脑准备扩展屏';
      await this.writeFrame(handle, encodeControl('ready', 1, true, true));

      const decoder = new FrameDecoder();
      const video = new VideoAssembler(2 * 1024 * 1024);
      this.status = '已就绪，等待电脑发送画面';
      while (this.running) {
        const buffer = new ArrayBuffer(16896);
        const count = await fileIo.read(handle.accessoryFd, buffer);
        if (!this.running) { break; }
        if (count <= 0) { throw new Error('USB 流已关闭'); }
        decoder.push(new Uint8Array(buffer.slice(0, count)));
        let frame = decoder.take();
        while (frame !== undefined && this.running) {
          const payload = new Uint8Array(frame).slice(16);
          if (payload.length === 8 && payload[0] === 83 && payload[1] === 66 &&
              payload[2] === 67 && payload[3] === 49) {
            const control = decodeControl(payload);
            if (control.kind === 'stop') {
              this.status = '电脑已停止屏桥会话';
              this.running = false;
              break;
            }
          } else {
            try {
              const picture = video.push(payload);
              if (picture !== undefined && picture.kind === 'frame') {
                this.frames++;
                this.bytes += picture.payload.length;
                if (picture.keyframe) { this.pictures++; }
                this.status = `已收到 ${this.frames} 帧，关键帧 ${this.pictures}（待接入系统解码器）`;
              }
            } catch (pictureError) {
              this.status = '视频包无效，等待下一张关键帧';
            }
          }
          frame = decoder.take();
        }
      }
      if (this.status === '已就绪，等待电脑发送画面') { this.status = '已停止'; }
    } catch (e) {
      const error = e as BusinessError;
      this.status = `通信结束：${error.code ?? ''} ${error.message ?? e}`;
    } finally {
      this.stop();
      this.busy = false;
    }
  }

  build() {
    Column({ space: 20 }) {
      Text('屏桥').fontSize(34).fontWeight(FontWeight.Bold)
      Text('USB 扩展屏接收端').fontSize(20)
      Text(this.status).fontSize(20).width('90%')
      Text(`已接收 ${this.frames} 帧 / ${this.bytes} 字节 / 关键帧 ${this.pictures}`).fontSize(22)
      Button('连接屏桥').enabled(!this.busy).onClick(() => { this.connect(); })
      Button('停止会话').enabled(this.busy).onClick(() => {
        this.status = '正在停止';
        this.stop();
      })
      Text('首次使用需允许 USB 配件访问；电脑端助手会在设备出现后自动处理握手。').width('90%')
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).padding(32)
  }
}
