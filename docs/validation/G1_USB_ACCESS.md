# G1 USB 访问验证

## 当前结论

2026-11-04 完成 U1 只读诊断。平板已经连接，但当前枚举身份是调试身份 `12d1:5000`，配件身份 `18d1:2d00` 没有出现。`can_attempt_access` 对配件身份为 false。

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

## 下一步

U2 在出现可信签名包，或本机具备可检查 INF 的 WDK/SignTool 之前，不生成、不安装自定义驱动。平板保持当前调试身份。后续需要用户安装 Windows 11 驱动开发工具，或提供已经签好的包；安装仍限已验证的配件身份，不替换现有 HDC/MTP 驱动。
