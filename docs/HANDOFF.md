# 换电脑开发交接

最后整理：2026-11-02。

## 先读什么

1. 根目录 `AGENTS.md` 和 `README.md`。
2. [项目目标](PROJECT_GOALS.md)，特别是用户明确要求和未决问题。
3. [阶段路线图](ROADMAP.md)，从 M0 开始。

仓库目前是项目背景和目标的持久记录，还不是可以编译的应用。没有已选定的依赖、SDK 版本或运行脚本。

## 在另一台电脑获取工程

```powershell
git clone https://github.com/FTP-LI/Project-ScreenBridge.git
cd Project-ScreenBridge
git status --short --branch
```

若已有克隆，先查看工作区；本地改动妥善保存后，再执行：

```powershell
git pull --ff-only
```

提交和推送需要在新电脑配置自己的 Git 身份及仓库访问权限。设备配对、开发者登录、SDK 路径和签名材料不会随 Git 克隆迁移，需要在新电脑单独配置。

## 下一次开发先做什么

1. 确认电脑的 Windows 版本、架构、显卡，以及平板完整系统构建号。
2. 检查数据线是否具备数据传输能力，分别确认两类测试端口是否实际可用。
3. 检查本机开发环境。候选工具包括 DevEco Studio/HarmonyOS SDK，以及在确定 Windows 实现方式后所需的编译工具；只有选择驱动路径时才安排匹配的 Windows SDK/WDK。
4. 重新核对目标版本的公开 USB API，验证设备角色、授权、协议和 Windows 端连接方式。
5. 确定最小通信实验设计，再实现原型。先传输和校验测试数据，不必立即开发完整视频界面。
6. 把真实结果写入 `docs/validation/`，同时更新路线图中的状态。

需要用户协助的部分是连接平板、切换端口、设备授权和确认实机显示效果。不能用模拟输出替代这些结果。

## 给下一次开发会话的上下文

> 请先阅读本仓库的 AGENTS.md、README.md、docs/PROJECT_GOALS.md、docs/ROADMAP.md 和 docs/HANDOFF.md。项目名为 Project ScreenBridge，拟用品牌“屏桥”。用户希望华为 HarmonyOS 7 平板通过普通 USB 数据线成为 Windows 扩展屏，并同时兼容有 PD、无 PD 的 USB 数据接口。平板可安装应用，电脑端最好免安装，但这不是已经解决的条件，也未确认用户接受一次安装驱动。现阶段尚无原型或实测结果。请从 M0 的设备与环境核对、公开 USB 接口可行性和最小通信实验设计继续，明确区分用户要求、技术假设与实测结论。不要把 USB 网络共享等同于原生 USB 直连，也不要把已有第三方软件的能力当成本项目的能力。

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
