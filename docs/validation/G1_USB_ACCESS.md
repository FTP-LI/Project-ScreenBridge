# G1 USB 访问验证

## 当前结论

2026-11-04 上午的 U1 只读诊断里，平板当时枚举为调试身份 `12d1:5000`，配件身份没有出现。同一天晚些时候已安装限定配件身份的 WinUSB 包，握手后设备变为 `18d1:2d00` 且问题码 0。随后 100 帧和 140 帧边界回传都已在这台配件上校验通过。换端口、重启保留、传输中拔线和无 HDC 的正常模式起连仍未做。细节见下文。

调试身份问题码 0，服务为 WINUSB，驱动为 Microsoft `winusb.inf`，设备接口存在，兼容 ID 含 `USB\MS_COMP_WINUSB`。本轮 libusb 只列出这一台 `12d1:5000`。这只说明当前用户会话能枚举调试身份，不是配件回传，也不是 echo 通过。

本机没有 Visual Studio / `cl.exe`、Windows 10 SDK、WDK、SignTool、InfVerif、Inf2Cat。`C:\Windows\INF` 中没有匹配 `VID_18D1&PID_2D00` 或 `VID_18D1&PID_2D01` 的 INF。U2 因此暂停实际安装。缺工具不是签名拒绝，也不是安装通过。

U1 只表示诊断就绪。没有勾选 USB 通道通过，没有切换配件模式，没有启动 HDC，没有改动驱动。

## 设备和工具

| 项目 | 本轮实际值 |
| --- | --- |
| 观察时间 | 2026-11-04T07:13:51Z 起 |
| Windows | Windows 11 专业工作站版，10.0.26200，x64 |
| 电脑 | 七彩虹 BATTLE-AX B850M-PLUS S WIFI7，与 2026-11-02 记录为同一开发机 |
| 当前 USB 身份 | `12d1:5000`，状态 OK，问题码 0，服务 WINUSB，INF `winusb.inf`，Provider Microsoft |
| 配件身份 | `18d1:2d00` 未枚举；`18d1:2d01` 未另作安装目标 |
| HDC 进程 | 未运行；本轮没有启动 HDC |
| 线材、端口、PD、速率 | 本轮没有新的测量 |
| Python / PyUSB | 3.12.10 / 1.3.1，`work/venv/Scripts/python.exe` |
| DevEco / Node | 26.0.0.851 / v24.14.1 |
| PowerShell | Windows PowerShell 5.1.26100.6584。PowerShell 7 不存在，检查脚本由 5.1 执行 |
| C++ / SDK / WDK | Visual Studio、`cl.exe`、`C:\Program Files (x86)\Windows Kits\10` 均不存在 |
| 签名与 INF 工具 | SignTool、InfVerif、Inf2Cat 均不存在 |
| 其他套件 | Windows Kits 8.1 存在，不能当作 Windows 11 WDK |

## 命令与结果

| 检查 | 结果 | 记录 |
| --- | --- | --- |
| 配件身份只读检查 | `present_count=0`，`can_attempt_access=false`，`hdc_process_running=false` | [18d1:2d00](results/2026-11-04-g1-env-18d1-2d00.json) |
| 当前连接身份只读检查 | 1 台，问题码 0，接口存在，`can_attempt_access=true` | [12d1:5000](results/2026-11-04-g1-env-12d1-5000.json) |
| libusb `list` | 成功，仅 `12d1:5000` | [list](results/2026-11-04-g1-libusb-list.json) |
| 只读 `probe` | 成功，协议版本 2。没有发送 START，没有切换配件模式 | [probe](results/2026-11-04-g1-probe.json) |
| `C:\Windows\INF` 搜索 `VID_18D1&PID_2D0[01]` | 无匹配 | 本轮终端输出，未改 INF |
| Python 协议/探针测试 | 12 项通过，0.002 秒 | 本轮实际运行，不是沿用 11 月 2 日计数 |
| 平板协议测试 | 3 项通过 | `test-protocol.mjs`，本轮实际运行 |

复现命令以仓库根目录执行。`0x18d1/0x2d00` 是计划规定的目标；`0x12d1/0x5000` 是本轮为了记录实际连接身份而追加的同脚本检查。

```powershell
powershell -NoProfile -File .\scripts\windows\Inspect-UsbEnvironment.ps1 -OutputPath work\g1-env.json -VendorId 0x18d1 -ProductId 0x2d00
powershell -NoProfile -File .\scripts\windows\Inspect-UsbEnvironment.ps1 -OutputPath work\g1-env-debug-identity.json -VendorId 0x12d1 -ProductId 0x5000
$env:SCREENBRIDGE_LIBUSB = 'C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains\libusb_shared.dll'
.\work\venv\Scripts\python.exe .\prototypes\usb\host\usb_probe.py list --report work\g1-libusb-list.json
.\work\venv\Scripts\python.exe -m unittest discover -s prototypes/usb/host -v
& 'C:\Program Files\Huawei\DevEco Studio\tools\node\node.exe' --test prototypes/usb/harmony/test-protocol.mjs
```

`can_attempt_access=true` 只表示恰好一台当前设备问题码为 0、已有服务且登记了设备接口。调试身份的这个值不能用来打开配件通道。公开 JSON 不含实例路径、序列号或计算机名。

## 仍未验证

- 配件态 `18d1:2d00` 的驱动、接口 GUID、标准用户打开和 echo。
- 关闭 HDC/调试后的正常模式起连。
- 跨端口、重启后的绑定保留。
- 30 分钟持续传输、20 次插拔、PD 与线速。
- Windows 扩展桌面。

历史问题码 28 仍然只属于 2026-11-02 的配件身份记录。本轮设备不在那个身份上，不能把“当前未枚举”写成问题码已经消失或驱动已经修好。

## 软件传输层

2026-11-04 在配件接口仍不可用时，先把 echo 循环抽成可注入的传输层。`accessory_transport.py` 负责唯一设备选择、分片读写、CRC 校验和关闭。主机测试先因模块缺失失败，随后 Python 21 项和 Node 协议 3 项通过。平板协议没有改动。

这些测试使用假端点。它们不表示真机 echo、边界包长或拔线恢复已经通过。

## 配件驱动安装

2026-11-04 在签名工具就绪后生成 `drivers/windows/usb/ScreenBridgeUsb.inf`。它只匹配 `USB\VID_18D1&PID_2D00` 和 `USB\VID_18D1&PID_2D01`，接口 GUID 为 `{331c44be-387b-4621-84a7-f55422e41cfc}`。

| 检查 | 结果 |
| --- | --- |
| InfVerif 10.0.26100.6584 `/w` 与 `/h` | INF 有效，退出码 0 |
| Inf2Cat `/os:10_GE_X64` | 目录生成完成，无错误、无警告 |
| 目录签名 | 本机自签 `CN=ScreenBridge Development`。导入本机受信任存储后，`signtool verify /pa` 通过。这不是公开发布签名，证书不入库 |
| `pnputil /add-driver ... /install` | 成功，发布名称 `oem121.inf` |
| 握手后的当前身份 | `18d1:2d00`，问题码 0，WINUSB，`oem121.inf`，Provider ScreenBridge，接口 GUID 与 INF 一致 |
| libusb list | 仅 `18d1:2d00`。[list](results/2026-11-04-g1-list-after-start.json) |
| 1 帧 echo，64 字节，超时 3 秒 | `USBTimeoutError`，已校验帧数 0。[echo](results/2026-11-04-g1-echo-probe.json) |

握手记录见 [start](results/2026-11-04-g1-start.json)。调试身份 `12d1:5000` 没有被这个 INF 匹配。主机进程在非管理员会话中发起了传输并得到超时，说明接口可以被当前用户打开；平板端当时没有回传，所以不能记为 echo 通过。换端口和重启保留尚未测试。

## 真机回传

2026-11-04T11:32:12Z，平板应用已打开配件后，100 帧、每帧 4096 字节全部校验通过，耗时 0.578 秒，单向负载 409600 字节。记录见 [100 帧](results/2026-11-04-g1-echo-basic.json)。

同一出口端点的 `wMaxPacketSize` 为 512。第一次边界测试在 48 字节完成 20 帧后，于 496 字节停住：负载加 16 字节帧头正好是一个包。已安装的平板应用把读取结果小于等于 0 当成断开，所以主机不能补零长度包，而是把最后一字节单独再写一次，让这次读取以短包结束。

第二次测试通过了 512、1024 和 4096 字节整帧，并校验了 1 帧 16384 字节后超时，已校验帧数 81。16384 正好等于当时的主机读取长度。读满后，平板写入末尾的零长度包还留在管道里，平板侧的写入不返回。单独再读一次得到长度 0。主机读取长度改为 16896，大于平板单次写入的 16384，零长度包就能在同一次读取里结束传输。

2026-11-04T11:42:19Z 用修改后的主机重新发送每个边界尺寸 20 帧，140 帧全部校验通过，耗时 3.297 秒，单向负载 3061120 字节。记录见 [边界回传](results/2026-11-04-g1-echo-boundaries.json)。平板回到调试身份后再次打开配件，2026-11-04T12:05:29Z 同一组边界又通过 140 帧，耗时 3.265 秒。紧接着 60 秒、每帧 4096 字节的连续回传完成 11782 帧，单向负载 48259072 字节，往返 1.5341 MiB/s。记录见 [60 秒](results/2026-11-04-g1-echo-60s.json)。这 60 秒内线一直插着，不能当作拔线恢复。

## 下一步

边界回传和这次 60 秒连续回传已通过。传输中拔线没有发生。下一次仍要在持续发送时拔掉数据线，再插回并重新打开配件。无 HDC 的正常模式还要另一次关闭 USB 调试。这两项都还没有证据。
