# 屏桥计划 Project ScreenBridge

让鸿蒙平板通过普通 USB 数据线成为 Windows 电脑的扩展屏，同时将支持 PD 和不支持 PD 的电脑 USB 数据接口纳入兼容目标。

**当前状态：M0 技术验证进行中，已有最小 USB 实验源码和可签名安装的平板应用，尚无扩展屏或发布版本。** 实测已完成配件握手和模式切换；完整回传与 Windows 驱动条件见[验证报告](docs/validation/M0_USB_2026-11-02.md)。下文的完整产品能力仍是目标。

## 产品与命名

| 用途 | 当前工作名称 |
| --- | --- |
| 项目 | 屏桥计划 / Project ScreenBridge |
| 鸿蒙平板应用 | 屏桥 / ScreenBridge |
| Windows 配套程序 | 屏桥助手 / ScreenBridge Helper |

软件名称暂用，商标、应用市场及域名重名情况尚未核查。

## 核心目标

- 通过有线连接实现真正的扩展桌面，电脑与平板可以显示不同窗口。
- 同时支持有 PD 和无 PD 的 USB 数据接口，不把 PD 当作画面传输的必要条件。
- 优先使用普通 USB 数据线，不将额外采集卡或转接硬件作为当前方案前提。
- 平板可安装原生鸿蒙应用；日常使用尽量接线即可连接。
- 电脑首次安装和配置必要组件，之后允许低占用后台监测；用户日常连接数据线并打开平板应用，电脑应自动建立扩展桌面。
- 以未来可公开发布为目标，先验证底层能力，再开发完整产品。

PD 主要涉及供电协商。USB 数据带宽、接口供电方向和是否支持视频输出是不同能力。没有 PD 不应成为软件拒绝连接的理由，但可能无法在使用时维持平板电量。

## 从哪里开始

| 文档 | 内容 |
| --- | --- |
| [项目目标](docs/PROJECT_GOALS.md) | 用户明确需求、当前设备、首版建议范围和未决问题 |
| [阶段路线图](docs/ROADMAP.md) | 技术验证、个人可用、公开测试、正式发布及验收目标 |
| [开发交接](docs/HANDOFF.md) | 换电脑后的恢复步骤、下一步任务和研究资料 |
| [协作说明](AGENTS.md) | 后续开发者与 AI 助手应保留的项目边界 |
| [USB 实验原型](prototypes/usb/README.md) | 构建、部署、握手和回传测试命令 |
| [本轮验证记录](docs/validation/M0_USB_2026-11-02.md) | 环境、真实结果、失败记录和后续关口 |
| [推荐实现方案](docs/RECOMMENDED_APPROACH.md) | 一次配置、低占用后台、自动扩展及硬件输入备选 |
| [实现目标规划](docs/IMPLEMENTATION_PLAN.md) | G1–G6 里程碑、交付物、依赖和验收门槛 |
| [下一轮 USB 实施计划](docs/superpowers/plans/2026-11-02-usb-foundation.md) | 从环境与 WinUSB 访问开始的 U1–U5 执行清单 |

## 当前技术方向

推荐链路为：屏桥助手监听插拔 → 自动建立 USB 会话 → 平板就绪 → Windows IDD 创建独立显示器 → GPU 编码 → USB 数据通道 → 鸿蒙应用解码显示。无显示会话时仅保留事件监测。

用户已接受电脑一次配置和低占用后台，并选定该主线开展实现规划；具体实现仍需通过验证，尤其是 WinUSB 访问、无 HDC 的正常模式起连、IDD 和完整画面链路。当前按总体目标 G1 的 USB 实施计划从 U1 开始；规划完成不代表这些组件已实现。OpenHarmony 文档中的接口不能直接视为目标 HarmonyOS 平板已验证可用。

## 换电脑继续开发

首次获取工程：

当前原型、推荐方案和实施计划已合入 `main`，新电脑从主分支继续开发：

```powershell
git clone --branch main https://github.com/FTP-LI/Project-ScreenBridge.git
cd Project-ScreenBridge
git status --short --branch
```

已有克隆且工作区干净时切换并更新（已有本地分支时直接切换，只有远程分支时 Git 会建立跟踪）：

```powershell
git fetch origin
git switch main
git pull --ff-only
```

然后按上表顺序阅读文档。M0 原型依赖和构建命令见[原型说明](prototypes/usb/README.md)。本地签名配置不会随 Git 迁移，新电脑先运行构建脚本生成配置，再在 DevEco 配置自己的开发签名。

## 许可证

仓库已有 [GNU AGPL v3 许可证](LICENSE)。本次文档整理保留原许可证。依赖选型和发布方式应与仓库许可证一起评估。

记录日期：2026-11-02。
