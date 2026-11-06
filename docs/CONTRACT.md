# 跨端契约 / Python → C++ 迁移准绳

记录日期：2026-11-06。本文件是 [持续开发计划](../.workbuddy/plans/quantum-thunder-newton-ze29Q2aV.md) 第七节的落地规格，也是把 Windows 常驻助手从 Python 原型迁到 C++/原生 WinUSB 时唯一准绳。

**适用范围**：Windows 主机侧（助手编排、PnP、状态机、USB 传输）。鸿蒙平板 ArkTS 侧不迁移，但必须与本文件字节级一致。`prototypes/usb/host/usb_probe.py` 与 `accessory_transport.py` 保留为开发诊断工具，不作为常驻组件选型（见 `docs/RECOMMENDED_APPROACH.md`）。

**规则**：下表常量与语义均来自现有源码，属于「已实现契约」；任何一端变更必须同步 Python / ArkTS / C++ 三端并重跑协议测试，否则视为破坏互操作。标注「未验证」的条目不得写成产品能力。

## 一、线格式（字节级）

| 名称 | 定义 | 来源 |
| --- | --- | --- |
| SBC1 控制消息 | **8 字节** `struct.Struct("<4sBHB")`（4+1+2+1）：magic `b"SBC1"`、kind（capability=1 / ready=2 / stop=3）、version uint16、flags uint8。`decode_control` 按 `_PACK.size` 校验长度。`paired=0x01`、`accept=0x02`，`flags>0x03` 非法。版本门槛 `SUPPORTED_CONTROL_VERSION=1` | `apps/windows/helper/control_message.py` |
| SBP1 传输帧 | 16 字节头 `struct.Struct("<4sIII")`：magic `b"SBP1"` + seq + length + CRC32（IEEE，黄金向量 `123456789 → 0xCBF43926`），全小端。`MAX_PAYLOAD=65536`、`READ_CHUNK=16384+512=16896`、`WRITE_CHUNK=16384` | `prototypes/usb/host/protocol.py` |
| SBP1 包边界 | 主机读取长度必须大于平板单次写入 16384（故 16896），否则零长度包滞留导致写入不返回；负载加帧头恰为端点整包长度（实测 512）时，把最后一字节单独再写一次以短包收尾。坏帧终止当前会话，不静默恢复 | `accessory_transport.py`、`docs/validation/G1_USB_ACCESS.md` |
| SBV1 视频消息 | 22 字节头 `struct.Struct("<4sBBIQHH")`：magic `b"SBV1"`、kind（CAPABILITY=1 / FRAGMENT=2 / STOP=3）、flags（`FLAG_KEYFRAME=0x01`）、access_unit、timestamp_us(uint64)、index、count。`MAX_SBP1_PAYLOAD=65536`、`MAX_FRAGMENT_PAYLOAD=65514`、分片数 ≤256；能力负载 `<HHB`(max_width,max_height,max_fps) | `shared/protocol/video_packet.py` |
| SBV1 装配 | 只保留最新未完成的 access unit；新单元到达丢弃旧单元；元数据不一致/分片冲突/超限即失同步；关键帧前丢弃差分帧，丢帧后必须等到下一关键帧；缓冲有界 | `video_packet.py`、`prototypes/usb/harmony/entry/src/main/ets/protocol.ts` |
| FrameSlot | `publish(width,height,stride,data,size)` 校验 `data!=null && w>0 && h>0 && stride>=width && size==stride*height && size<=capacity`；CRC32 多项式 `0xEDB88320`、初值/终值 `0xFFFFFFFF`；单帧覆盖 + `sequence` 递增，`latest()` 重算校验；`not a queue` | `apps/windows/streaming/frame_slot.h` |

## 二、身份与常量

| 项 | 值 | 来源 |
| --- | --- | --- |
| 设备接口 GUID | `{331c44be-387b-4621-84a7-f55422e41cfc}` | `apps/windows/helper/pnp_source.py`、`drivers/windows/usb/ScreenBridgeUsb.inf` |
| DEBUG_IDS | `{(0x12D1, 0x5000)}` | `apps/windows/helper/session_machine.py`、`host_step.py` |
| ACCESSORY_IDS | `{(0x18D1, 0x2D00), (0x18D1, 0x2D01)}` | `session_machine.py`、`accessory_transport.py` |
| AOA 身份串 | `("ScreenBridge","USBProbe","ScreenBridge M0 echo","0.1","https://github.com/FTP-LI/Project-ScreenBridge","m0-prototype")`；GET_PROTOCOL 请求 51、身份请求 52、START 请求 53；协议版本须为 1 或 2 | `prototypes/usb/host/usb_probe.py` |
| stable_key | `sha256(instance_id)[:16]`，公开记录只含哈希；实例 ID、序列号、计算机名留在进程/本机 | `pnp_source.py` |
| STOP_REASONS | `("unplug","stop","background","read_hang")` | `session_machine.py` |

`18d1:2d00/2d01` 是共享 AOA 身份，**不能作为配对唯一身份**；INF 只精确匹配这两个 VID/PID，不匹配 `12d1:5000`、通配类 FF 或全部华为设备。

## 三、行为契约（语义级）

1. **PnP 顺序**：先注册 `CM_Register_Notification`，再枚举一次已连接设备；订阅期间的通知排队，snapshot → queued 顺序回放；按 `device.key` 去重，移除后允许再次到达。回调只投递 `(kind, instance_id)`，问题码与接口存在性在工作线程读取。无设备时阻塞等待，不轮询。
2. **8 态单会话**：`disconnected / discovered / waiting_reenumeration / needs_setup / waiting_tablet / establishing / running / cleaning`。会话活跃期间异构设备 → `reject_ambiguous`；同一 key 重入不重开；未配对 → `reject_unpaired`；配件态 `problem_code!=0` 或接口缺失 → `needs_setup`，不重试、不反复切模式。
3. **控制校验**：非 `waiting_tablet` 的控制消息 → `reject_control`；`kind!=ready || version!=1 || !paired || !accept` → `reject_tablet`；`stop` → `cleaning → disconnected`。`capability` 目前按拒绝处理，不是能力协商。
4. **取消与释放**：`TransferGate` 停止幂等（reason 只设一次）；`run_cancellable` 异常记 `error_type`，**finally 关闭 transport**；被取消或未完成的帧**不计入 verified**；仅当前设备移除时才 `gate.stop("unplug")` 并关闭一次。真实 WinUSB 必须用 OVERLAPPED + `CancelIoEx`/`WinUsb_AbortPipe`，**不能用 UI「停止」代替实际读写结束**。
5. **close 幂等**：`AccessoryTransport` 用 `_closed` 保证 `releaser()` 只调一次；`run_echo` 在 finally 取得关闭责任；重复 close 或上下文退出不重复释放句柄。
6. **唯一设备**：`choose()` 命中数 ≠1 抛错；歧义或空匹配时不发送任何数据；空 selector / 空 allowed_ids 拒绝。
7. **会话就绪才挂屏**：关键帧到达前 `display_connected=False`；打开失败 `machine.stop("stop")` 收回；停止或拔出清掉已标记显示器并释放编解码资源。
8. **低占用**：助手首选登录用户进程，不引入长期以管理员身份运行的系统服务；IDD 自身在驱动宿主 Session 0，桌面/托盘逻辑不放进驱动。

## 四、未验证项（不得写成能力）

- 真机热插拔、平板停止后的恢复、真实 WinUSB 可取消读（现为 `threading.Event` 假门闩）。
- 关闭 USB 调试后的无 HDC 正常模式起连、跨端口/重启的驱动绑定保留。
- 平板端 SBC1 发送方（`encode_control` 在鸿蒙侧零命中）、正式平板工程 `apps/harmony/screenbridge/`（尚不存在）。
- 驱动到用户进程图像交接、GPU 编码、H.264 解码与 Surface 显示、完整画面链路。
- 本机自签 `CN=ScreenBridge Development` 不是可发布签名。

## 五、迁移触发条件（全部满足才逐模块替换）

1. G1 的四个独立结论字段（`accessory_access_passed`、`echo_passed`、`normal_mode_bootstrap_passed`、`cross_port_retention_passed`）各有明确真机结论。
2. G2 真机自动会话收敛到单会话（线先插/应用先开、重复通知去重、未配对拒绝、拔线重连）有证据。
3. G3 标准用户进程读到连续多帧有证据。
4. 1080p30 功能样机在 Python 原型 + 原生 WinUSB 通道上打通，线格式与取消语义无歧义。

触发后逐模块用 C++ 重写为登录用户进程，Python 诊断 CLI 保留作对照；每替换一个模块都重跑三端协议测试与本文件逐字段核对，不一次性重写。

## 六、回归检查清单

- Python：`prototypes/usb/host`（23 项）、`tests/windows/helper`（27 项）、`tests/windows/streaming`（7 项）。
- Node：`prototypes/usb/harmony/test-protocol.mjs`（6 项）。
- C++：`apps/windows/streaming/frame_slot_test.cpp` 编译运行；后续新增 `tests/windows/display/`。
- 上述均为**软件测试**，不得替代真机验收；真机证据另按 `docs/validation/` 七类分账记录。
