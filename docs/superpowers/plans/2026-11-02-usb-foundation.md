# G1 USB 基础验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task; use superpowers:subagent-driven-development only when the user has chosen delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决当前 Windows 配件态访问阻点，取得真实双向数据校验及无 HDC 的正常模式起连证据，为后台和视频子系统提供可靠前提。

**Architecture:** 继续使用已存在的 Python/PyUSB 主机工具和原生 ArkTS 配件回传应用。先检查环境与完整 WinUSB 配置，再提取可测的传输入口、完成边界收发与正常模式实验；本计划不创建 Windows 显示器。

**Tech Stack:** 已记录 Python 3.12.10 / PyUSB 1.3.1，DevEco 26.0.0.851、SDK 26.0.0.105/API 26、内置 Node 24.14.1；计划核对 WinUSB、INF/目录签名工具及后续 IDD 的 WDK/SDK/C++ 工具。

**Spec:** [已选实现主线](../../RECOMMENDED_APPROACH.md)、[总体实施目标 G1](../../IMPLEMENTATION_PLAN.md)、[当前验证证据](../../validation/M0_USB_2026-11-02.md)。

## Global Constraints

- 首版限定当前 Windows 11 x64 和当前参考平板，不据此承诺其他 Windows 版本/架构兼容。
- 保留普通 USB 原生数据链路；HDC 仅部署/诊断，不用于实验数据转发。
- 配件身份 `18d1:2d00/2d01` 是共享身份；设备缺失、歧义或身份不符时不发送测试数据。
- SBP1 是 `SBP1` 魔数、序号/长度/负载 CRC32 各 4 字节小端，头共 16 字节，负载最多 65,536 字节；保留现有黄金向量及跨端协议测试。
- 用户接受一次电脑配置；不关闭驱动签名验证或改测试模式，不覆盖整类 USB 设备的绑定。
- 签名材料、真实序列号、配对密钥及未经脱敏的设备路径留在忽略目录；仓库只存源码与脱敏报告。

## Review Focus

| 失败条件 | 需要证明的行为 | 负责任务 |
| --- | --- | --- |
| 代码 28、缺接口 GUID、标准用户无权限 | 诊断能区分；未实际打开不能标“驱动可用” | U1/U2 |
| 其他 AOA 设备或多台相同 VID/PID | 拒绝歧义；不发送测试数据，不默认取第一台 | U2/U3 |
| 帧长为端点包长或读取块的整数倍 | 不因缺少短包边界挂起；不能把超时丢失的数据当通过 | U3 |
| 停止、拔线、部分写入和错误校验 | 返回失败、释放资源，重连可继续；无旧句柄重用 | U3 |
| 关闭 HDC 后正常模式、换端口或重启 | 同样可握手并重枚举；两阶段分别留下证据 | U4/U5 |

## 文件边界

| 文件 | 操作与职责 |
| --- | --- |
| `scripts/windows/Inspect-UsbEnvironment.ps1` | 新建：只读工具和目标 PnP/接口诊断，输出脱敏 JSON，不安装驱动或改变 USB 模式 |
| `drivers/windows/usb/README.md` | 新建：已验证身份、接口 GUID、匹配范围、签名来源、安装/恢复与工具命令 |
| `drivers/windows/usb/ScreenBridgeUsb.inf` | 仅在确需自定义包时新建；复用系统 WinUSB，限定已验证身份/接口；CAT 等产物放忽略的 build 目录 |
| `prototypes/usb/host/accessory_transport.py` | 新建：把 USB 接口打开和校验回传循环从 CLI 拆出；不负责自动安装或显示状态 |
| `prototypes/usb/host/test_accessory_transport.py` | 新建：失败与边界契约测试，使用可注入端点，不伪装硬件结果 |
| `prototypes/usb/host/usb_probe.py` | 修改：调用可测传输入口，支持单轮多负载边界验证并输出完整结果 |
| `prototypes/usb/harmony/entry/src/main/ets/pages/Index.ets` | 需要时修改：停止/断线/部分收发处理，保持实验 UI 的诊断标识 |
| `prototypes/usb/harmony/entry/src/main/ets/protocol.ts` | 仅真实边界缺陷需要时修改；不改坏既定帧格式 |
| `docs/validation/G1_USB_ACCESS.md` | 新建：本计划唯一汇总报告，引用脱敏 JSON；原始日志仍在 work 中 |

执行者以仓库根目录为工作目录；`./work/venv/Scripts/python.exe` 为实验解释器。新文件路径是规划，不代表当前已存在。静态 INF、文档和只读检测脚本采用真实工具检查与输出审查，不额外写只镜像实现的单元测试；协议和资源生命周期必须有行为测试。

### U1：环境与驱动状态基线

**Files:** 新建 `scripts/windows/Inspect-UsbEnvironment.ps1`、`docs/validation/G1_USB_ACCESS.md`。

**Interfaces:** `Inspect-UsbEnvironment.ps1 -OutputPath <path> -VendorId <uint16> -ProductId <uint16>`；输入为显式目标身份，输出包含 `observed_at_utc`、工具路径/版本、`devices`（VID/PID、问题码、服务、INF、接口是否存在）、`can_attempt_access`。不采集真实序列号；缺工具/设备是记录内容，不伪造可用。

- [x] 阅读当前报告，重新核实目标是否连接；定位 DevEco/Python、C++、Windows SDK/WDK、InfVerif/Inf2Cat/SignTool。读取指定身份的状态和接口，默认不启动 HDC。2026-11-04：配件身份未枚举，当前连接为 `12d1:5000`；签名和 WDK 工具缺失。
- [x] 实现只读检测脚本，仅输出接口存在性及必要状态；临时完整路径若被诊断工具读到，不写入公开 JSON。
- [x] 运行检查脚本并审查脱敏字段。本机没有 PowerShell 7，改由 Windows PowerShell 5.1 执行同一脚本；`18d1:2d00` 缺设备，已在报告中写明。
- [x] 运行现有 Python 与 Node 协议测试。本轮结果为 12 项和 3 项通过。
- [x] 将脱敏摘要写入报告；形成独立提交。报告已写入 `docs/validation/G1_USB_ACCESS.md`。U1 只表示诊断就绪，不勾选 USB 通过。

### U2：建立可访问的 WinUSB 配件接口

**Files:** 新建 `drivers/windows/usb/README.md`；确需自定义包时新建 `drivers/windows/usb/ScreenBridgeUsb.inf`；更新 `docs/validation/G1_USB_ACCESS.md`。

**Interfaces:** 消费 U1 的实际工具/设备状态；交付 WinUSB 设备接口 GUID、包来源/签名/匹配范围以及标准用户能够打开该接口的证据。GUID 必须写入该目录 README，供 U3 读取；共享 AOA VID/PID 不能充当配对身份。

- [ ] 先核对现有可信签名包能否正确覆盖目标及接口 GUID；如需要新包，在实际工具就绪后生成仅针对验证目标的 INF，注册应用接口和正常用户访问权限。
- [ ] 确认共享身份的影响范围、原驱动与恢复方法。不能用通配类 FF 或所有华为设备匹配，不能自动替换正在使用的其他 MTP/HDC/显示驱动。
- [ ] 按已安装工具版本检查 INF 和目录签名，保存准确命令、退出码、签名者及包哈希。构建目录与签名证书不入库。没有可信签名包或工具时，交付源码与明确缺项，暂停实际安装，不将此记成拒签或安装通过。
- [ ] 在用户已授权的一次配置范围内安装该目标；记录安装前后问题码、服务、INF 与接口变化。安装需要系统授权时按实际权限办理，不重复询问已接受的部署原则。
- [ ] 用标准用户进程实际打开并关闭目标接口，再换参考端口、重启重插核对保留。不只看设备名称或问题码消失。记录结果并提交脱敏材料。

### U3：真实回传与 USB 包边界

**Files:** 新建 `prototypes/usb/host/accessory_transport.py`、`prototypes/usb/host/test_accessory_transport.py`；修改 `usb_probe.py`，必要时修正平板读写；更新报告。

**Interfaces:** 在新文件中定义 `AccessorySelector(allowed_ids: tuple[tuple[int, int], ...], interface_number: int = 0)`。`open_accessory(backend, selector: AccessorySelector) -> AccessoryTransport`，对象暴露 `read(size: int, timeout_ms: int) -> bytes`、`write(data: bytes, timeout_ms: int) -> int`、幂等 `close() -> None`，支持上下文管理。底层枚举复用已有唯一设备检查；空 selector/空 allowed_ids 拒绝，M0 CLI 仅显式使用两种 AOA 身份、接口 0，且只连接一台目标；这不是产品配对认证。

`run_echo(transport, *, sizes: tuple[int, ...], count: int, timeout_ms: int, duration_s: float | None = None) -> EchoResult`。定义结果类型字段 `ok: bool`、`verified_frames: int`、`verified_payload_bytes: int`（成功帧负载的单向字节总和）、`elapsed_seconds: float`、`error_type: str | None`。`count` 是每个 sizes 元素的帧数，按给定大小顺序执行；sizes 非空且各值为 1–65,536，count/timeout 为正。`duration_s` 仅允许单一 size，保持现有单大小长测兼容。该函数取得本轮 transport 的关闭责任，finally 关闭；退出上下文或重复 close 不重复释放底层句柄。失败保留已校验数量，`ok=False`，CLI 返回非零。

- [ ] 先写失败行为测试：`test_ambiguous_device_never_writes`、`test_crc_error_is_not_counted_as_verified`、`test_partial_io_reconstructs_frame`、`test_disconnect_closes_once_and_fails`；断言拒绝歧义时发送次数为 0，错误帧不计数，退出路径均关闭资源且重复关闭安全。

计数测试在该测试文件内定义只用于测试的回环 transport（write 收到的字节供 read 返回），并保留关闭计数；核心断言如下，真实 USB 验收另做：

```python
transport = self.make_loopback_transport()
result = run_echo(transport, sizes=(48, 496), count=2, timeout_ms=500)
self.assertTrue(result.ok)
self.assertEqual(result.verified_frames, 4)
self.assertEqual(result.verified_payload_bytes, (48 + 496) * 2)
transport.close()
self.assertEqual(transport.release_count, 1)
```

- [ ] 运行 `./work/venv/Scripts/python.exe -m unittest discover -s prototypes/usb/host -p test_accessory_transport.py -v`，确认因新接口缺失失败后，提取最小传输层并实现这些契约；保留既有命令兼容。CLI 新增 `--sizes` 接受逗号分隔的上述整数负载集合，传入 run_echo；与显式 `--size` 或 `--duration` 同时使用应报参数错误，未显式设置的默认 size 不造成冲突。加入 `test_multi_size_count_and_bytes`、`test_duration_rejects_multiple_sizes` 和 `test_invalid_sizes_close_safely`，覆盖数量/字节统计和资源责任。
- [ ] 运行完整 Python 和共用 TypeScript 测试。只在发现真实或测试可复现的缺陷时改平板协议/生命周期；改动后用 `./prototypes/usb/Build-Harmony.ps1` 重建，按现有签名部署说明安装，签名材料继续忽略。
- [ ] 真机先做 `usb_probe.py echo --count 100 --size 4096 --report work/g1-echo-basic.json`，再做 `usb_probe.py echo --count 20 --sizes 48,496,1008,4080,16368,65520,65536 --report work/g1-echo-boundaries.json`（均以实验 Python 执行，并按现有说明提供 libusb）。后者预期共 140 个已校验帧，覆盖 64/512/1024 包长及 16 KiB 读取块的整包边界。记录真实端点包长；若挂起，定位短包/零长包与读取超时行为后修复，不跳过边界或静默丢数据。
- [ ] 传输中拔线并重新连接、在平板停止，分别记录错误及下一轮能否恢复。关闭取消语义若不足，以实测决定增加原生可取消 I/O，不能用界面显示“停止”替代实际读写结束。
- [ ] 脱敏记录：每轮负载、帧数、耗时、错误、端口和线材；提交源码/测试/报告。所有假端点测试通过也不能代替此真机步骤。

### U4：无 HDC 的正常模式起连

**Files:** 更新 `drivers/windows/usb/README.md`、`prototypes/usb/README.md` 和 `docs/validation/G1_USB_ACCESS.md`；只有真实访问需求改变时修改 USB 包或探针。

**Interfaces:** 消费 U2 的访问配置及 U3 的可靠回传；输出正常模式初始 VID/PID/接口 → 握手 → 配件重枚举 → 真机校验的完整证据，单列 `normal_mode_bootstrap_passed`。不把 `12d1:5000` 调试态写成产品唯一入口。

- [ ] 在用户配合下关闭平板 USB 调试并停止本机 HDC，拔插回到用户日常 USB 模式；重新用只读检查记录身份及已有驱动。不要假定硬件 ID 与之前相同。
- [ ] 根据该身份选择可发布的主机访问路径；若需要新的受控绑定，先补充 INF/签名和其他功能影响记录，不无差别覆盖 MTP。
- [ ] 用主机工具在该模式发起公开配件握手，等待同一目标重枚举后完成 U3 的基础校验。全程不启动 HDC、不用 HDC 转发，也不在成功后才停止调试冒充无依赖。
- [ ] 分别记录线先插/平板应用先开的尝试，至少确认手动开发工具可完成原生流程；自动 PnP 后台属于 G2，不提前声称已实现。
- [ ] 无法取得正常模式访问路径时，给出“配件态回传通过，但正常起连未通过”等准确结论并停止将 AOA 标为可用产品通道；保留 IDD 独立验证计划。成功或失败均提交可复现报告。

### U5：G1 证据汇总和下阶段输入

**Files:** 汇总 `docs/validation/G1_USB_ACCESS.md`；更新 `docs/ROADMAP.md`、`docs/HANDOFF.md`。

**Interfaces:** 消费 U1–U4 的原始与脱敏记录；输出 `accessory_access_passed`、`echo_passed`、`normal_mode_bootstrap_passed`、`cross_port_retention_passed` 四个独立结论及下阶段可用接口，缺证据的值只能是 `not_tested` 或 `failed`。

- [ ] 按版本、设备/端口/线材、身份/驱动、步骤、预期、实测、日志路径和限制核对证据；原始路径/序列号不入公开材料。
- [ ] 进入 G2 功能原型须有真实配件访问、U3 全部校验、无 HDC 正常模式起连。跨端口或重启保留未通过时，不宣布产品已满足一次配置；缺端口明确记待测，可继续原型/独立显示开发，但不能勾选该兼容验收。
- [ ] 不重复 30 分钟/20 次插拔的全面测试：此轮先建立功能证据，G6 再做统一稳定性验收；发现新变化或失败时按问题补测。
- [ ] 更新状态并提交。按上述原型门槛进入 G2 独立实施计划；G3 工具/显示实验可独立推进，完整产品放行仍依赖 USB、配置保留与后续兼容证据。
