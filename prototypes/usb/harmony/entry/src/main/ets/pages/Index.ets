import { usbManager } from '@kit.BasicServicesKit';
import { fileIo } from '@kit.CoreFileKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { FrameDecoder } from '../protocol';

@Entry
@Component
struct Index {
  @State status: string = '等待电脑切换到 ScreenBridge 配件模式';
  @State frames: number = 0;
  @State bytes: number = 0;
  @State busy: boolean = false;
  private running: boolean = false;
  private handle: usbManager.USBAccessoryHandle | undefined = undefined;

  private stop(): void {
    this.running = false;
    const handle = this.handle;
    this.handle = undefined;
    if (handle !== undefined) {
      try { usbManager.closeAccessory(handle); }
      catch (e) { this.status = `关闭失败：${(e as BusinessError).code}`; }
    }
  }

  aboutToDisappear(): void { this.stop(); }

  private async connect(): Promise<void> {
    if (this.busy) { return; }
    this.busy = true;
    this.running = true;
    this.frames = 0;
    this.bytes = 0;
    try {
      const matches = usbManager.getAccessoryList().filter((item: usbManager.USBAccessory) =>
        item.manufacturer === 'ScreenBridge' && item.product === 'USBProbe');
      if (matches.length !== 1) { throw new Error(`匹配配件数：${matches.length}，请先在电脑执行 start`); }
      const accessory = matches[0];
      if (!usbManager.hasAccessoryRight(accessory)) {
        this.status = '请允许 USB 配件访问';
        if (!await usbManager.requestAccessoryRight(accessory)) { throw new Error('USB 配件授权被拒绝'); }
      }
      if (!this.running) { return; }
      const handle = usbManager.openAccessory(accessory);
      this.handle = handle;
      this.status = '已打开配件，等待电脑执行 echo';
      const decoder = new FrameDecoder();
      while (this.running) {
        const buffer = new ArrayBuffer(16384);
        const count = await fileIo.read(handle.accessoryFd, buffer);
        if (!this.running) { break; }
        if (count <= 0) { throw new Error('USB 流已关闭'); }
        decoder.push(new Uint8Array(buffer.slice(0, count)));
        let frame = decoder.take();
        while (frame !== undefined && this.running) {
          let offset: number = 0;
          while (offset < frame.byteLength && this.running) {
            const written = await fileIo.write(handle.accessoryFd, frame.slice(offset, offset + 16384));
            if (written <= 0 || written > Math.min(16384, frame.byteLength - offset)) {
              throw new Error('USB 写入未前进或长度异常');
            }
            offset += written;
          }
          if (!this.running) { break; }
          this.frames++;
          this.bytes += frame.byteLength - 16;
          this.status = '校验并回传中';
          frame = decoder.take();
        }
      }
      this.status = '已停止';
    } catch (e) {
      const error = e as BusinessError;
      this.status = `通信结束：${error.code ?? ''} ${error.message}`;
    } finally {
      this.stop();
      this.busy = false;
    }
  }

  build() {
    Column({ space: 20 }) {
      Text('屏桥 · USB 通信验证').fontSize(30).fontWeight(FontWeight.Bold)
      Text('M0 开发原型，仅验证数据回传').fontSize(18)
      Text(this.status).fontSize(20).width('90%')
      Text(`已回传 ${this.frames} 帧 / ${this.bytes} 字节负载`).fontSize(22)
      Button('查找配件并开始回传').enabled(!this.busy).onClick(() => { this.connect(); })
      Button('停止并关闭配件').enabled(this.busy).onClick(() => {
        this.status = '正在停止；如读取未结束，请拔线后重试';
        this.stop();
      })
      Text('保持前台。失败后先停止，必要时拔插数据线。电脑端需先执行 start，再执行 echo。').width('90%')
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).padding(32)
  }
}
