# Windows USB 访问

记录日期：2026-11-04。本目录提供只匹配配件身份的 WinUSB INF。目录文件和开发证书留在本机 `work/usb-driver/`，不入库。

## 应用接口 GUID

`{331c44be-387b-4621-84a7-f55422e41cfc}`

这是 `ScreenBridgeUsb.inf` 为配件接口登记的 DeviceInterfaceGUIDs。它不是调试身份 `12d1:5000` 上系统自动生成的接口，也不能代替平板配对身份。

## 匹配范围

| 硬件 ID | 处理 |
| --- | --- |
| `USB\VID_18D1&PID_2D00` | 使用收件箱 WinUSB |
| `USB\VID_18D1&PID_2D01` | 使用收件箱 WinUSB |
| `USB\VID_12D1&PID_5000` | 不匹配。调试身份继续使用系统 `winusb.inf` |
| `USB\VID_12D1&PID_107E` | 仅由单独的 `ScreenBridgeBootstrap.inf` 开发候选包声明；当前尚未安装或验证 |

只声明 `NTamd64`。不使用类 `FF` 通配，不匹配其他华为设备，不替换 MTP、HDC 或显示驱动。`18d1:2d00` 与 `18d1:2d01` 仍是共享配件身份。

## 本机安装结果

InfVerif `10.0.26100.6584` 的 `/w` 与 `/h` 均判定 INF 有效。Inf2Cat 以 `10_GE_X64` 生成目录，错误和警告均为空。目录由本机自签证书 `CN=ScreenBridge Development` 签名，证书只导入这台电脑的受信任根和受信任发布者。这不是可公开发布的微软签名。

`pnputil` 添加成功，发布名称为 `oem121.inf`。随后从 `12d1:5000` 完成配件握手后，当前设备枚举为 `18d1:2d00`，问题码 0，服务 WINUSB，INF `oem121.inf`，Provider 为 ScreenBridge，接口 GUID 与上表一致。libusb 能列出这一台。一次 64 字节 echo 在 3 秒后返回 `USBTimeoutError`，已校验帧数为 0；主机已经打开设备，平板应用当时没有在读回传。

换端口和重启后的保留还没有测。

## 正常模式开发候选包

2026-11-13 关闭 USB 调试后的实测身份为 `12d1:107e`，但本机绑定的 Huawei `oem46.inf` 报问题码 39（状态 `0xC000007B`），没有产生可打开的复合子接口。`ScreenBridgeBootstrap.inf` 只声明这一组 VID/PID，并复用屏桥接口 GUID；其设备安全描述只给交互式用户读写权限，目的是在获得明确授权后做一次可回滚的 WinUSB 访问实验。

该包当前只做 INF 静态范围记录，**没有安装、没有删除 `oem46.inf`，也没有替换系统驱动**。由于目标是复合设备，绑定父设备可能影响 MTP/其他功能；任何安装实验都必须先保存当前设备驱动信息、以管理员会话执行，并准备按实际发布名称回滚。成功安装后仍要重新验证 AOA GET_PROTOCOL/START、设备重枚举和平板应用访问，不能把包生成或签名视为 U4 通过。

## 恢复

移除本机这个包：

```powershell
pnputil /delete-driver oem121.inf /uninstall /force
```

发布名称若已变化，先用 `pnputil /enum-drivers` 按 Provider `ScreenBridge` 核对。证书文件在 `work/usb-driver/`，不要提交。
