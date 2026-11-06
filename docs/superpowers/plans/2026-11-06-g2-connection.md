# G2 连接控制与后台实施计划（S3）

> 状态：待执行。目标：接通「两套世界」——已存在的注入式状态机 / 真实 ctypes PnP / 真实 PyUSB 端点，串成从设备到达 → 自动 AOA 握手 → 从 USB 读 SBC1 → 平板就绪 → 单会话的链路。契约见 `docs/CONTRACT.md`，先用 Python 取证再迁 C++。

**Goal**：插线后助手自动完成握手与重枚举，只在已配对平板发送 `ready` 后建立会话；两种启动顺序收敛到同一会话，拔线清理后可重连；无设备时事件等待。

## 文件边界

| 文件 | 操作 |
| --- | --- |
| `apps/windows/helper/main.py` | 新增编排入口：`pnp_source.subscribe_targets()` / `list_targets()`（现全仓无调用点）→ `DeviceWatch` → `HostSession.handle` → `accept_frame` |
| `apps/windows/helper/winusb_transport.py` | 新增：`CreateFile` 打开 `{331c44be-...}` 设备接口 → `WinUsb_Initialize` → OVERLAPPED 可取消 `WinUsb_ReadPipe/WritePipe` → `CancelIoEx` / `WinUsb_AbortPipe` → 幂等 `close()` |
| `apps/windows/helper/pairing.py` | 新增：`stable_key` 配对注册/持久化/忘记配对，数据放本地忽略目录，不入库 |
| `apps/windows/helper/aoa_handshake.py` | 新增：移植 `usb_probe.py` 的 51/52/53 控制请求与身份串；仅在 DEBUG 身份且状态机需要时发起 |
| `apps/windows/helper/control_message.py` 等 7 个现有模块 | 契约基准，尽量不改；线格式与状态语义见 CONTRACT.md |
| `apps/harmony/screenbridge/` | 新增：平板端 SBC1 发送方，`encode_control` 与 Windows 侧字节级一致；DevEco Studio 及内置 SDK 构建 |
| `tests/windows/helper/test_orchestrator.py` | 新增：注入式编排测试 |
| `docs/superpowers/plans/2026-11-02-usb-foundation.md` | U4/U5 定义保持不动，真机结论写入 `docs/validation/G1_USB_ACCESS.md` |

## 步骤

- [ ] 先写失败行为测试：线先插 / 应用先开 / 助手晚启动 / 重复 PnP 通知都收敛到一个会话；未配对 → `reject_unpaired`；坏 SBC1 帧、版本不符、未授权不打开通道；停止与移除只关闭一次；取消读不把未完成帧计入 verified。
- [ ] 实现 `main.py` 编排入口（先订阅再枚举、回调只投递事件、状态读取放工作线程），给 `subscribe_targets()` 建立真实调用点。
- [ ] 实现 `winusb_transport.py`（Python 原型）：可取消 OVERLAPPED 读替换 `threading.Event` 门闩；保留 `read/write/close` 契约与 `close` 幂等；歧义设备不写。
- [ ] 补 SBC1 入站通道：`transport.read` → `FrameReader` → `decode_control` → `HostSession.accept_frame/accept_ready` → `SessionMachine.control`。
- [ ] 实现 `pairing.py`（`stable_key` 持久化，不靠共享 AOA VID/PID 判断唯一身份）与 `aoa_handshake.py`（配件态不重复握手）。
- [ ] 用 DevEco 内置 SDK 新建 `apps/harmony/screenbridge/`：实现 SBC1 `capability/ready/stop` 发送方与 Node 协议测试；`module.json5` 权限按实际需要补充。**已安装的实验 HAP 不含这些代码，需重建签名安装后才可联调。**
- [ ] 离线跑全部 Python/Node 测试；接入真实 Windows PnP 与设备接口后，在本机管理员条件下核对接口打开与问题码（不需平板）。
- [ ] 平板到位后做真机联调：自动握手 → 平板 ready → 8 态单会话 → 拔线 `cleaning` → 重连；分别记录两种启动顺序。

## 验收

- **离线**：注入式编排测试全绿；真实 CM API 有调用点；取消语义在可取消读上被覆盖；`close` 幂等、歧义拒绝不发送。
- **真机联调**（并入 P4 放行证据）：不要求用户手动 `start`/`echo`；未配对或授权拒绝不投送桌面；拔线可重连。
- **禁止**：把 63 项假端点/本地协议测试写成自动连接通过；不用 HDC 转发或 USB 网络共享代替原生 USB；自动 PnP 后台未验证前不声称「插线即用」。
