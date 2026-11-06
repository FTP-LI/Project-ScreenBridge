# 换电脑开发交接

最后整理：2026-11-06。

## 先读什么

1. 根目录 `AGENTS.md` 和 `README.md`。
2. [项目目标](PROJECT_GOALS.md)，特别是用户明确要求和未决问题。
3. [阶段路线图](ROADMAP.md)，从 M0 开始。
4. [推荐实现方案](RECOMMENDED_APPROACH.md)，包括最新接受的电脑部署原则和两条 USB 验证关口。
5. [G1 USB 访问验证](validation/G1_USB_ACCESS.md) 与 [G3 屏桥显示器验证](validation/G3_IDD_2026-11-04.md)，先按真机证据判断进度。
6. [实现目标规划](IMPLEMENTATION_PLAN.md)及[当前 USB 实施清单](superpowers/plans/2026-11-02-usb-foundation.md)，从 U3 收尾与 U4 继续。

仓库已有 M0 最小 USB 实验源码、WinUSB 包、屏桥 IDD、连接状态机和视频协议原型，位于 `prototypes/usb/`、`drivers/windows/`、`apps/windows/` 与 `shared/protocol/`。详见[运行说明](../prototypes/usb/README.md)、[首轮验证报告](validation/M0_USB_2026-11-02.md)和上述 G1/G3 报告。配件态双向回传已有真机证据，但还不能显示扩展桌面，无 HDC 的正常模式起连也未验证。

## 在另一台电脑获取工程

当前源码、规划与验证记录都在 `main`（2026-11-06 合并）；换电脑前先确认远端 `main` 已同步，新电脑直接获取这个分支：

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

**当前下一任务：** 2026-11-04 配件 `18d1:2d00` 已完成 100 帧、140 帧边界、重开后 140 帧和 60 秒连续回传（11782 帧、单向 48259072 字节、往返 1.5341 MiB/s），出口包长 512，记录见 [G1_USB_ACCESS.md](validation/G1_USB_ACCESS.md)。屏桥 IDD 曾以非主屏接入本机桌面、验证后移除，见 [G3_IDD_2026-11-04.md](validation/G3_IDD_2026-11-04.md)。下一步是 U3 收尾（传输中拔线、平板停止后的恢复、脱敏汇总）、U4（关闭 USB 调试与 HDC 后从日常模式起连）和 U5（四个独立结论）。换端口、重启保留、跨两类端口的长测仍无证据。USB 包与 IDD 包都是本机自签，证书不入库，公开发布签名未解决。2026-11-06 只读复查时没有在线的 `12d1`/`18d1` 设备，`hdc` 未运行，屏桥显示器也未接入。

1. 读取报告：开发机为七彩虹 B850M、Windows 11 10.0.26200。MSVC 14.44、WDK/SDK 10.0.26100、InfVerif/Inf2Cat/SignTool 已于 11-04 补齐；`oem121.inf`（USB）与 `oem138.inf`（IDD）由本机自签证书 `CN=ScreenBridge Development` 签名。历史问题码 28 属于 11-02，本轮未复测。
2. 当前阻点：U3 的拔线与停止恢复、U4 无 HDC 正常模式起连、U5 汇总、跨端口/重启保留，以及 IDD 图像从驱动宿主交到用户进程。不能把 11-04 上午的工具缺失或更新向导取消记录当成签名被拒。
3. 平板应用已签名安装，11-04 真机 echo 已通过；11-06 复查时平板未以调试或配件身份在线，需要用户重新接线并在平板上打开屏桥。11-05 早上的 `start` 仍是调试身份 `12d1:5000`，不构成 U4 证据。
4. 新电脑按原型 README 建立 Python 虚拟环境、运行测试与构建脚本。SDK 使用 DevEco 内置 API 26；鸿蒙侧只用 DevEco Studio 及其内置 SDK，本地签名配置被忽略，不能通过 Git 迁移。
5. 100 帧、边界帧和 60 秒连测已有证据；下一步先补拔线/停止恢复与正常模式起连，30 分钟长测和两类端口各 20 次插拔统一留到 G6，不重复计算。当前端口 PD 与线速仍未知。
6. G3 可独立推进图像交接，不能借用机器已有的 Todesk/GameViewer 虚拟显示适配器认定屏桥实现扩展显示。驱动库里还堆着 11 个旧版本 IDD 包（`oem122.inf`–`oem137.inf` 中的旧版），持续开发计划已授权清理；用 `scripts/windows/Clean-OldDisplayDrivers.ps1 -Apply` 在管理员会话执行，默认保留 `oem121.inf` 与 `oem138.inf`，只允许删除 Provider=ScreenBridge 的废弃 IDD 包，不碰其他驱动。

需要用户协助的部分是连接平板、切换端口、设备授权和确认实机显示效果。2026-11-06 时平板未连接，开始 U3/U4 前需先接线并在平板上打开应用。S0 的废弃 IDD 包清理当前会话不是管理员，请在管理员 PowerShell 中运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\Clean-OldDisplayDrivers.ps1 -Apply`（本机执行策略为 Restricted，进程级 Bypass 不改系统配置；不带 `-Apply` 只预览，默认保留 `oem121.inf` 与 `oem138.inf`）；清理后按 G3 计划回归显示器接入。不能用模拟输出替代这些结果。

## 给下一次开发会话的上下文

> 先读 AGENTS.md、README.md、目标、路线图、HANDOFF、方案、IMPLEMENTATION_PLAN.md、G1_USB_ACCESS.md、G3_IDD_2026-11-04.md 和首轮验证报告。用户已选定一次电脑配置、低占用后台、USB 扩展主线，目标 R01–R09 未变，无需重新选方案。2026-11-06 已把 `g1-usb-access` 的最新工作合入 `main`、清理误入库的构建产物，并跑通本机自动化基线（Python 23+27+7 项、Node 6 项，均为假端点/本地测试，不是真机验收）。真机已有配件态 WinUSB 访问、标准用户打开接口和 echo 回传证据；尚无无 HDC 正常模式起连、自动连接、驱动图像交接、完整画面链路或扩展桌面。当前下一任务是 U3 收尾 → U4 → U5；G3 可并行。PD/非 PD、低占用、1080p60 都是待验收目标。USB 与 IDD 包仍是本机自签，公开发布签名和一次配置的跨端口保留未解决；不提交签名材料或设备个人标识。

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
- 留在本机：账号凭证、签名私钥、设备个人数据、临时抓取内容、未经整理的调试日志和本地工作笔记。
- 构建产物（`*.obj`、`*.dll`、`*.exe`、TMH、MAP 等）由 `.gitignore` 排除，不入库；`.workbuddy/` 属于本地工作笔记，同样不入库。
- 原有 `LICENSE` 为 GNU AGPL v3，本次整理未更改；引入代码或依赖时记录来源与许可证。
