# 换电脑开发交接

最后整理：2026-11-04。

## 先读什么

1. 根目录 `AGENTS.md` 和 `README.md`。
2. [项目目标](PROJECT_GOALS.md)，特别是用户明确要求和未决问题。
3. [阶段路线图](ROADMAP.md)，从 M0 开始。
4. [推荐实现方案](RECOMMENDED_APPROACH.md)，包括最新接受的电脑部署原则和两条 USB 验证关口。
5. [实现目标规划](IMPLEMENTATION_PLAN.md)及[当前 USB 实施清单](superpowers/plans/2026-11-02-usb-foundation.md)，从 G1/U1 继续。

仓库已有 M0 最小 USB 实验源码，位于 `prototypes/usb/`，可构建并签名安装到当前平板。详见[运行说明](../prototypes/usb/README.md)和[本轮验证报告](validation/M0_USB_2026-11-02.md)。它还不能显示扩展桌面，也未完成完整 USB 回传。

## 在另一台电脑获取工程

当前实施规划在 `main`，已合入 `main`。新电脑直接获取这个分支：

```powershell
git clone --branch main https://github.com/FTP-LI/Project-ScreenBridge.git
cd Project-ScreenBridge
git status --short --branch
```

若已有克隆，先查看工作区；本地改动妥善保存后，再执行：

```powershell
git fetch origin
git switch main
git pull --ff-only
```

提交和推送需要在新电脑配置自己的 Git 身份及仓库访问权限。设备配对、开发者登录、SDK 路径和签名材料不会随 Git 克隆迁移，需要在新电脑单独配置。

## 下一次开发先做什么

**最新用户要求：** 已接受电脑一次配置后日常免配置，允许低占用后台监测。平板打开应用/启用后，电脑应自动出现扩展显示器；`start` / `echo` 仅留作诊断工具。见目标 R05/R08/R09。不要再次把首次电脑配置视为尚未获接受的原则问题，实际驱动包仍需合法签名和实测。

**当前下一任务：** G1/U1 只读诊断已在 2026-11-04 完成，证据见 [G1_USB_ACCESS.md](validation/G1_USB_ACCESS.md)。不要重做环境扫描，也不要跳到界面或视频。U2 在 Windows 11 SDK/WDK 与 SignTool/InfVerif/Inf2Cat 可用，或已有可信签名包之前，暂停生成和安装 INF。

1. 读取报告：开发机仍是七彩虹 B850M、Windows 11 10.0.26200。2026-11-04 平板以调试身份 `12d1:5000` 连接，问题码 0，WINUSB，libusb 能列出这一台。配件身份 `18d1:2d00` 当时未枚举。历史握手版本 2 和问题码 28 仍是 2026-11-02 的记录。
2. 当前阻点：本机没有 Windows 10 SDK/WDK、MSVC、SignTool、InfVerif、Inf2Cat。`C:\Windows\INF` 没有配件身份的匹配 INF。不能把缺工具写成签名拒绝。历史更新向导以 0x4c7（取消）结束，仍然不能认定签名包被拒。
3. 平板应用已签名安装。2026-11-02 用户确认当时已打开配件并等待 echo。2026-11-04 这次连接停在调试身份，没有新的配件打开或回传记录。完成配件态访问后，还要验证非调试正常 USB 模式的起连。
4. 新电脑按原型 README 建立 Python 虚拟环境、运行测试与构建脚本。SDK 使用 DevEco 内置 API 26；本地签名配置被忽略，不能通过 Git 迁移。
5. 数据通道可打开后，先跑 100 帧校验，再测 30 分钟和各类端口的插拔。当前端口 PD 与线速仍未知。
6. 独立开始 Windows IDD 验证，不能借用机器已有的第三方虚拟显示驱动认定屏桥实现扩展显示。

需要用户协助的部分是连接平板、切换端口、设备授权和确认实机显示效果。不能用模拟输出替代这些结果。

## 给下一次开发会话的上下文

> 先读 AGENTS.md、README.md、目标、路线图、HANDOFF、方案、IMPLEMENTATION_PLAN.md、G1_USB_ACCESS.md 和 11 月 2 日验证报告。用户已选定一次电脑配置、低占用后台、USB 扩展主线。G1/U1 诊断已完成：2026-11-04 平板在 `12d1:5000`，配件身份未枚举，签名工具缺失，U2 暂停安装。历史上已有 Python/PyUSB、ArkTS 原型和本轮重新跑过的 12+3 项软件测试、签名 HAP、协议版本 2、配件打开反馈；尚无完整回传或扩展桌面。配件态代码 28 与正常模式无 HDC 起连是两个独立关口，本轮没有复测代码 28。后续在工具就绪后继续 U2，再进入 U3–U5。PD/非PD、低占用和 1080p60 都是待验收目标。保留正常签名机制；不提交签名材料或设备个人标识。

## 前期研究线索

以下链接来自本项目讨论中的技术调研，供后续核对。接口和发布规则可能变化，实际实现需要按选定 SDK 和目标设备重新确认。

| 资料 | 用途与限制 |
| --- | --- |
| [微软间接显示驱动模型 IDD](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/indirect-display-driver-model-overview) | Windows 虚拟显示器的候选实现基础，不能据此推导电脑端免安装 |
| [微软 IndirectDisplay 示例](https://github.com/microsoft/Windows-driver-samples/tree/main/video/IndirectDisplay) | 驱动结构与实现参考；示例不是可直接发布的成品 |
| [OpenHarmony USB 管理接口](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-basic-services-kit/js-apis-usbManager.md) | 包含配件授权和通信接口；不等于 HarmonyOS 7 平板实测支持 |
| [华为受限开放权限说明](https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/restricted-permissions) | 核对 API/权限是否允许目标设备使用和发布；尤其关注 USB DDK 的设备类别限制 |
| [华为应用审核指南](https://developer.huawei.com/consumer/cn/doc/app/50104) | 正式发布前按实际分发场景核对 |
| [Moonlight V+ 鸿蒙版](https://github.com/AlkaidLab/moonlight-harmony) | 原生鸿蒙视频接收的调研对象，非本工程已选依赖 |
| [Foundation Sunshine](https://github.com/AlkaidLab/foundation-sunshine) | 虚拟显示和串流体验的调研对象，非本工程已选依赖 |

前期曾制作第三方软件操作指南，但它不构成本项目的实现方案或运行依赖。后续开发应以本仓库的目标和实测记录为依据。

## 仓库与本地材料

- 应提交：源码、项目文档、可复现的构建说明、脱敏后的验证记录。
- 留在本机：账号凭证、签名私钥、设备个人数据、临时抓取内容和未经整理的调试日志。
- 原有 `LICENSE` 为 GNU AGPL v3，本次整理未更改；引入代码或依赖时记录来源与许可证。
