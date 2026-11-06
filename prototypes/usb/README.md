# 屏桥 M0：最小原生 USB 通信原型

开发实验，尚不提供扩展桌面。Windows 主机用 PyUSB/libusb 发送配件控制请求，鸿蒙平板应用使用公开 `usbManager` accessory API 和 `fileIo` 读写。HDC 仅部署应用和读取诊断信息，数据不经过 HDC 转发。

**日常使用目标已明确为“在平板启用，电脑自动出现扩展屏”。** 本页的 `start` 是开发者手动发起 USB 模式切换，`echo` 是校验回传测试，都不是产品操作流程。当前原型还没有自动握手和平板启用控制协议；Windows 显示驱动、连接状态机在 `drivers/windows/display/`、`apps/windows/helper/` 另有实验源码，不属于本原型。不能把完成这些命令等同于实现扩展屏。

用户现已接受电脑首次配置和低占用后台。后续架构、两种硬件/软件显示方式的区别与验证顺序见[推荐方案](../../docs/RECOMMENDED_APPROACH.md)。

## 已验证与未验证

详细记录见 [首轮验证报告](../../docs/validation/M0_USB_2026-11-02.md) 和 [G1 USB 访问验证](../../docs/validation/G1_USB_ACCESS.md)。协议单元测试、HAP 构建、真机配件协议查询、WinUSB 安装和真机回传是独立关口；不能用其中一个替代完整画面链路成功。PD、供电和 USB 数据速率分别记录。

## 开发环境

本轮使用 Python 3.12.10、PyUSB 1.3.1、DevEco Studio 26.0.0.851、内置 Node 24.14.1、Hvigor 6.26.8、ohpm 26.0.0.630、SDK 26.0.0.105/API 26。

构建使用 DevEco 内置 SDK；兼容和目标 API 暂设 20（本轮实机报告 API 24，尚未做其他版本兼容测试）。这些是开发依赖，不代表最终 Windows 产品的安装方案。

在仓库根目录运行：

```powershell
python -m venv work/venv
./work/venv/Scripts/python.exe -m pip install -r prototypes/usb/host/requirements.txt
./work/venv/Scripts/python.exe -m unittest discover -s prototypes/usb/host -v
& 'C:\Program Files\Huawei\DevEco Studio\tools\node\node.exe' --test prototypes/usb/harmony/test-protocol.mjs
./prototypes/usb/Build-Harmony.ps1
```

DevEco 安装目录不同时，传 `-DevEcoHome '实际目录'`。脚本只在文件缺失时从 `build-profile.template.json5` 创建本地 `build-profile.json5`，不覆盖已有签名。生成的 HAP 在 `harmony/entry/build/default/outputs/default/`。

首次构建默认未签名。用 DevEco 打开 `prototypes/usb/harmony`，在 Project Structure → Signing Configs 配置开发签名并 Apply。`build-profile.json5`、证书和构建产物被 Git 忽略；不要把签名密码复制进模板。

## 实机实验步骤

先关闭其他占用此设备的调试/USB 程序。只连接一台目标华为平板，解锁并授权 HDC。不能同时操作其他项目的调试会话。

```powershell
$hdcExe = 'C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains\hdc.exe'
$env:SCREENBRIDGE_LIBUSB = 'C:\Program Files\Huawei\DevEco Studio\sdk\default\openharmony\toolchains\libusb_shared.dll'
$probe = 'prototypes/usb/host/usb_probe.py'
$pythonExe = './work/venv/Scripts/python.exe'

# 需要先生成 signed.hap。unsigned.hap 不能安装到当前零售平板。
& $hdcExe install prototypes/usb/harmony/entry/build/default/outputs/default/entry-default-signed.hap
& $hdcExe shell aa start -b com.screenbridge.usbprobe -a EntryAbility

# HDC 在本机独占 WinUSB；先释放，再进行原生 USB 实验。
& $hdcExe kill
& $pythonExe $probe list
& $pythonExe $probe probe --report work/probe.json

# 显式改变平板 USB 模式；会断开当前 HDC/MTP 连接。
& $pythonExe $probe start --report work/start.json
& $pythonExe $probe list
```

正常候选结果是出现 `18d1:2d00` 或 `18d1:2d01`。START 成功仅表示控制请求完成，还需检查重枚举、Windows 驱动绑定及应用访问。若设备尚未出现，等数秒再 `list`；本工具不自动安装或替换驱动。

配件态访问已在 2026-11-04 打通：限定 VID/PID 的 `ScreenBridgeUsb.inf`（本机自签）安装为 `oem121.inf`，问题码 0，标准用户可打开接口。11-02 的代码 28 是历史记录。详细安装与恢复命令见 [Windows USB 访问说明](../../drivers/windows/usb/README.md)。

在平板点击“查找配件并开始回传”，允许 USB 配件访问。待显示“已打开配件”后：

```powershell
& $pythonExe $probe echo --count 100 --size 4096 --timeout-ms 5000 --report work/echo.json
# 边界集合与 --size、--duration 互斥。真机回传仍要先打开配件接口。
& $pythonExe $probe echo --count 20 --sizes 48,496,1008,4080,16368,65520,65536 --report work/echo-boundaries.json
# 仅在基本回传成功后做长测；在两类端口上分别保存记录。
& $pythonExe $probe echo --duration 1800 --size 65536 --report work/echo-30min.json
```

`ok: true`、`frames` 为校验通过帧数。速率是往返负载总字节/测试时间，不是 USB 标称带宽，也不是视频帧率；CRC32 不提供身份认证。失败退出码为 1，记录已校验帧数，不把部分成功当整轮通过。

测试结束先在平板停止，拔插线回到正常 USB 模式，再用 HDC 检查连接。一次授权是否能跨插拔复用仍待验证。

## 下一轮实机配合清单（U3 收尾与 U4）

以下动作需要用户配合，不能由主机模拟。开始前先接线、解锁平板、确认 `hdc` 未运行，并在平板上打开屏桥实验应用、允许 USB 配件授权。命令均在仓库根目录执行，沿用上节的 `$pythonExe`、`$probe` 与 `SCREENBRIDGE_LIBUSB`。

U3 收尾 —— 拔线与停止恢复：

```powershell
& $pythonExe $probe echo --count 100 --size 4096 --report work/g1-echo-baseline.json
& $pythonExe $probe echo --duration 60 --size 4096 --report work/g1-echo-unplug.json
# 上一命令发送约 5 秒后拔掉数据线；插回、重新打开配件后再执行：
& $pythonExe $probe echo --count 100 --size 4096 --report work/g1-echo-after-unplug.json
```

再用“平板点停止”代替拔线，另存 `work/g1-echo-stop.json` 与 `work/g1-echo-after-stop.json`。验收点：错误帧不计入已校验帧数、进程不永久挂起、句柄只关闭一次、重连后基线再次通过。把脱敏结果复制到 `docs/validation/results/`，在 [G1 报告](../../docs/validation/G1_USB_ACCESS.md) 记录后再勾选 U3 第 4、5 项。

U4 —— 无 HDC 的正常模式起连：

1. 在平板关闭 USB 调试，停止本机 HDC，拔插数据线回到日常 USB 模式；不要假定硬件 ID 仍是 `12d1:5000`。
2. 用只读检查记录初始身份，再把实际 VID/PID 显式传给工具（下方 `0xVVVV`/`0xPPPP` 为占位）：

```powershell
powershell -NoProfile -File .\scripts\windows\Inspect-UsbEnvironment.ps1 -OutputPath work\g1-u4-normal.json -VendorId 0xVVVV -ProductId 0xPPPP
& $pythonExe $probe list
& $pythonExe $probe probe --vid 0xVVVV --pid 0xPPPP --report work/g1-u4-probe.json
& $pythonExe $probe start --vid 0xVVVV --pid 0xPPPP --report work/g1-u4-start.json
& $pythonExe $probe list
& $pythonExe $probe echo --count 100 --size 4096 --report work/g1-u4-echo.json
```

全程不启动 HDC、不用 HDC 转发；分别记录“线先插”和“平板应用先开”两种顺序。若正常模式无法取得可发布的访问路径，结论写成“配件态回传通过，但正常起连未通过”，保留 G3 独立研究，不把 AOA 标为可用产品通道。

## 常见结果

| 现象 | 含义与处理 |
| --- | --- |
| HDC 未授权 | 解锁平板并允许调试；仅影响开发部署 |
| 安装 9568320 / no signature file | HAP 未签名；配置开发签名后重新构建 |
| GET_PROTOCOL 返回 2 | 固件响应配件握手；不证明应用能够收发 |
| Access denied / errno 13 | 本轮由 HDC 占用引起；先 `hdc kill`，另查实际设备驱动 |
| No backend available | 指定与 Python 架构匹配的 libusb DLL；不随仓库分发 SDK DLL |
| 配件模式无法打开或无驱动 | 保留枚举与驱动信息；核对 `oem121.inf` 与接口 GUID，不自动替换系统驱动 |
| 平板匹配配件数为 0 | 尚未切换或本设备未向应用暴露配件；不改用 HDC 转发伪造通过 |
| 停止后仍等待读取 | 状态机的取消语义有假传输测试，但平板侧与真机拔线的取消能力未验证；必要时重启应用 |

## 协议与范围

16 字节头：ASCII `SBP1`、uint32 序号、uint32 负载长度、uint32 CRC32，所有整数小端。负载最多 65,536 字节；标准 CRC32/IEEE，黄金向量 `123456789 → 0xCBF43926`。平板只回传校验通过的完整帧。两端处理分片和部分写入；坏帧终止当前会话，不尝试静默恢复。

配件身份为 manufacturer `ScreenBridge`、model/product `USBProbe`、version `0.1`、serial `m0-prototype`（实验常量，不读取真实序列号）。只查询精确 VID/PID；发现零台或多台匹配设备即报错。`echo` 只认配件身份 `18d1:2d00/2d01` 的接口 0，开发时不要连接其他 AOA 配件。

不包含视频传输、Windows 显示驱动、后台常驻、插线自动启动、加密认证和发布签名。PyUSB 是实验工具依赖（BSD-3-Clause）；libusb 由本机 SDK 提供，未复制进仓库，产品分发时需另查其版本与 LGPL 许可义务。

参考：[AOA 官方协议](https://source.android.com/docs/core/interaction/accessories/aoa)、[AOA 2](https://source.android.com/docs/core/interaction/accessories/aoa2)、[OpenHarmony USB API](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-basic-services-kit/js-apis-usbManager.md)。HarmonyOS 可编译签名以本轮 SDK 的 `@ohos.usbManager.d.ts` 为依据，运行支持另做实测。
