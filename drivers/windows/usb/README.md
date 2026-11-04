# Windows USB 访问

记录日期：2026-11-04。本目录还没有屏桥 INF。配件身份的 WinUSB 安装尚未进行。

## 已观察身份

| 身份 | 本轮状态 |
| --- | --- |
| `18d1:2d00` | 未枚举。`C:\Windows\INF` 没有匹配 `VID_18D1&PID_2D00` 或 `VID_18D1&PID_2D01` 的 INF。没有当前问题码、服务或接口 |
| `12d1:5000` | 当前连接的调试身份。问题码 0，服务 WINUSB，INF `winusb.inf`，Provider Microsoft，设备接口存在，兼容 ID 含 `USB\MS_COMP_WINUSB` |

调试身份上的系统接口 GUID 不写入本文件。它不是屏桥配件通道的应用接口 GUID，U3 不能拿它打开配件。

## 签名与工具

未找到 Visual Studio、`cl.exe`、Windows 10 SDK、WDK、SignTool、InfVerif、Inf2Cat。没有可送检的自定义 INF，因此暂停生成和安装。Windows Kits 8.1 存在，不能当作 Windows 11 驱动工具链。缺工具不是签名拒绝。

证据见 [G1 USB 访问验证](../../../docs/validation/G1_USB_ACCESS.md)。

## 以后的匹配范围

自定义包只匹配已经在真机上验证过的配件身份和指定接口。不使用类 `FF` 通配，不匹配全部华为设备，不替换正在使用的 MTP、HDC 或显示驱动。`18d1:2d00` 与 `18d1:2d01` 是共享配件身份，不能当作唯一配对依据。

## 恢复

2026-11-04 这一轮没有安装或卸载驱动，没有需要回滚的 USB 变更。
