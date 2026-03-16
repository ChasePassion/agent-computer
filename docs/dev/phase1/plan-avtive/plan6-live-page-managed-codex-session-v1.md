# Plan 6: Live 页面托管 Codex Session 输入输出 v1

状态：active
创建日期：2026-03-16

## 1. 背景

当前项目已经完成两条基础链路：

- `screen live`：手机端可通过 `/live` 查看桌面最新画面
- `Codex output attach`：daemon 已可通过读取本地 `~/.codex/sessions/.../rollout-*.jsonl` 在 live 页面展示 Codex 输出摘要

对应现状代码：

- `src/agent_computer/api/live_page.py`
- `src/agent_computer/api/routes_observation.py`
- `src/agent_computer/services/live_output_service.py`
- `src/agent_computer/services/codex_session_watcher.py`

这说明“看屏幕 + 看输出”已经成立，但“从 live 页面直接给当前 Codex 发消息”还没有打通。

本次 phase1 的目标不是做一个完整 terminal 产品，而是在现有 observation/live 架构上，最小代价补齐：

1. live 页面查看更完整的 Codex 输出
2. live 页面向当前 Codex session 发送消息
3. 不依赖前台终端窗口
4. 不依赖 GUI 注入
5. 继续保持当前 `/live` 的轻量单页结构

## 2. 基于 Codex 源码的关键结论

本方案不再基于“猜测 Codex CLI 怎么工作”，而是直接以本地源码 `E:\code\codex` 为依据。

### 2.1 `app-server` 是官方的一等集成面

`codex-rs/app-server/README.md` 已明确说明：

- `thread/start`：新建会话
- `thread/resume`：恢复已有会话
- `turn/start`：发送一条新的用户输入
- `turn/steer`：向正在进行中的 turn 追加用户输入
- `turn/interrupt`：中断当前 turn
- 运行中输出通过 JSON-RPC notifications 流式下发

这意味着：

**正确的系统边界是“线程 / turn / notification”，不是“终端窗口 / 键盘输入 / 剪贴板粘贴”。**

### 2.2 官方 test client 已经演示了最小闭环

`codex-rs/app-server-test-client/src/lib.rs` 已经有两条最关键的参考实现：

1. `send_message_v2_with_policies(...)`
   - `initialize`
   - `thread/start`
   - `turn/start`
   - `stream_turn(...)`
2. `resume_message_v2(...)`
   - `initialize`
   - `thread/resume`
   - `turn/start`
   - `stream_turn(...)`

这基本就是我们需要的“自己包一层”的最小主链路。

### 2.3 官方 Python SDK 可复用，但不能原样照搬为 daemon 运行时

`sdk/python/src/codex_app_server/client.py` 提供了：

- 启动 `codex app-server --listen stdio://`
- `initialize()`
- `thread_start()`
- `thread_resume()`
- `turn_start()`
- `turn_steer()`
- `turn_interrupt()`
- typed notification parsing

但这个 SDK 当前是**单读取者阻塞模型**：

- `_request_raw()` 会读 stdout
- `next_notification()` 也会读 stdout
- `_read_message()` 是共享阻塞读

因此它适合脚本，不适合直接作为 daemon 的长期后台会话核心。

结论：

**可以复用它的启动参数、生成类型、通知映射思路，但 daemon 内部需要自己做一个 reader-thread + request/response 分发的薄 transport。**

### 2.4 TUI 的行为语义可借鉴，但不应整体复刻

`codex-rs/tui` 目前仍处于 hybrid 迁移期，内部状态较重。

可以借鉴的只是交互语义：

- 空闲时提交消息：新开 turn
- 运行中提交消息：走 steer
- 中断：走 interrupt
- 输出展示：优先渲染 `agentMessage delta`

不应复刻的部分：

- TUI 的复杂 pending steer 队列
- 本地 composer 状态机
- 终端 UI 细节

## 3. phase1 的产品定位

本次能力不是“远程控制一个终端窗口”，而是：

**Local Codex Session Manager for Live Page**

phase1 只做单活动会话。

live 页面绑定的是：

- 当前仓库下的一个 active Codex thread / session

而不是：

- 某个 terminal 窗口
- 某个 OS 前台进程句柄

## 4. phase1 的范围

## 4.1 要做

- 在现有 `/live` 页面增加输入区
- daemon 启动并持有一个 `managed Codex session`
- live 页面发送消息到 daemon
- daemon 通过 `app-server` 发给 Codex
- daemon 将输出增量整合进现有 `LiveOutputService`
- 支持 `interrupt`
- 支持从“只读 attach”切换到“托管 managed”

## 4.2 不做

- 多 session 切换
- 通用 terminal emulator
- GUI 注入
- OCR / terminal 文本抓取
- 审批 UI
- 完整历史回放
- WebSocket 版前端重构

## 5. 设计原则

### 5.1 Session-first

页面控制对象是 `Codex thread/session`，不是 terminal window。

### 5.2 Managed-first for write path

“发送消息”只对 daemon 托管的 `managed session` 生效。

### 5.3 Attach-readonly remains

现有 `CodexSessionWatcher` 保留，继续负责“附着到已有本地 session 并只读展示”。

### 5.4 Thin wrapper

尽量套用 Codex 已有协议和最小 client 逻辑，不重发明 runtime。

### 5.5 One active session only

phase1 只维护一个当前 managed session，避免前后端状态爆炸。

## 6. 总体架构

phase1 引入两种模式：

1. `attach_readonly`
2. `managed`

### 6.1 attach_readonly

沿用当前方案：

```text
existing codex interactive process
  ->
~/.codex/sessions/.../rollout-*.jsonl
  ->
CodexSessionWatcher
  ->
LiveOutputService
  ->
/live/state.json
```

特点：

- 零侵入
- 只能看，不能发
- 作为默认回退路径保留

### 6.2 managed

新增托管方案：

```text
live page
  ->
POST /live/session/message
  ->
CodexManagedSessionService
  ->
CodexAppServerTransport
  ->
codex app-server --listen stdio://
  ->
thread/start | thread/resume
  ->
turn/start | turn/steer | turn/interrupt
  ->
JSON-RPC notifications
  ->
CodexEventReducer
  ->
LiveOutputService
  ->
/live/state.json
```

## 7. 为什么 phase1 直接选 `app-server`

不选以下方案作为主路径：

- GUI focus + paste + enter
- Win32/ConPTY 直接托管 interactive TUI
- 读取 terminal 纯文本

原因：

1. 官方已有 `thread/turn` 协议，不需要自己定义“发消息给 Codex”的语义
2. `turn/steer` 是协议级能力，TTY 注入做不到等价语义
3. terminal 文本是表现层，不是系统边界
4. 当前项目已经有 output 聚合服务，只差 write path
5. `app-server-test-client` 已证明这条路足够薄

## 8. 关键设计决策

### 8.1 保留轮询，不上 SSE / WebSocket

phase1 继续使用现有 `/live/state.json` 轮询模型。

原因：

- 当前 `/live` 已是 1 秒轮询
- v1 重点是打通链路，不是前端推送性能
- 输出增量可以在 daemon 侧先聚合成最新状态
- 这样改动最小，和现有页面结构兼容最好

后续 phase1.5 再考虑把 output 区升级为 SSE。

### 8.2 output 采用“进行中缓冲 + 最近窗口”，不直接一条 delta 一条 UI

必须避免把 `agentMessage delta` 原样堆成 recent items。

推荐结构：

- `active_text`: 当前 turn 正在生成的 assistant 文本
- `latest_text`: 对页面显示的最新文本
- `recent`: 最近若干条已提交输出
- `status`
- `thread_id`
- `turn_id`
- `active_flags`

策略：

- 收到 `item/agentMessage/delta` 时只更新 `active_text`
- 收到 `turn/completed` 时把 `active_text` 合并成一条 recent
- `latest_text` 优先显示 `active_text`，否则显示最近 completed 文本

### 8.3 运行中发送消息默认走 `turn/steer`

路由规则：

1. 无 managed session
   - 新建 `thread/start`
   - 再 `turn/start`
2. 有 managed session，且当前 idle
   - `turn/start`
3. 有 managed session，且当前 active turn 存在
   - `turn/steer(expectedTurnId=active_turn_id)`

这和官方协议语义完全一致。

### 8.4 `attach_readonly -> managed` 通过 resume takeover 打通

如果 watcher 已发现当前仓库有一个 session id：

- 用户第一次在 live 页面点击发送
- daemon 尝试 `thread/resume(thread_id)`
- 成功后切入 managed 模式
- 后续消息都走 app-server

如果 resume 失败：

- 回退为 `thread/start(cwd=current_project)`

### 8.5 phase1 不做审批流 UI

这是本方案的边界收缩点。

原因：

- `app-server` 的 approval 是 server-initiated request
- 官方 Python SDK 当前默认 approval handler 会自动 accept 某些请求
- 若把审批 UI 一起做，phase1 复杂度会显著上升

phase1 选一条明确策略：

1. 默认使用 `approvalPolicy="never"` 运行 managed session
2. 若仍收到 approval request，则显式 reject，并在 live 页面显示“不支持审批，请回到本地 Codex”

推荐先采用策略 1。

## 9. 服务拆分

## 9.1 `CodexManagedSessionService`

建议位置：

- `src/agent_computer/services/codex_managed_session_service.py`

职责：

- 管理当前 managed session 生命周期
- 决定 `thread/start` / `thread/resume`
- 决定 `turn/start` / `turn/steer`
- 保存当前 `thread_id` / `active_turn_id`
- 对接 output reducer
- 对外提供 `send_message()` / `interrupt()` / `snapshot()`

建议内部状态：

- `mode: "attach_readonly" | "managed" | "none"`
- `thread_id: str | None`
- `thread_path: str | None`
- `active_turn_id: str | None`
- `thread_status_type: "active" | "idle" | "notLoaded" | "systemError" | None`
- `thread_active_flags: list[str]`
- `cwd: str`
- `updated_at: str | None`
- `last_error: str | None`
- `can_send: bool`
- `can_interrupt: bool`

## 9.2 `CodexAppServerTransport`

建议位置：

- `src/agent_computer/services/codex_app_server_transport.py`

职责：

- 启动 `codex app-server --listen stdio://`
- 完成 `initialize` + `initialized`
- 独占 stdout reader thread
- 维护 request id -> response future 映射
- 将 notification 推送给 reducer
- 处理 stderr tail

这是本方案最关键的新组件。

必须是：

- 单 reader
- 多 request caller
- 有写锁
- 可重启

不建议直接把 `sdk/python` 的 `AppServerClient` 当 transport 使用。

### 9.2.1 为什么需要自己包 transport

因为 `AppServerClient` 的 `_request_raw()` 和 `next_notification()` 都会消费同一个 stdout 流。

daemon 场景下我们需要：

- 一个后台线程持续消费 notification
- 同时 HTTP handler 能发新 request 并等待 response

所以必须拆成：

- `reader_loop`
- `pending_requests`
- `notifications_callback`

### 9.2.2 可复用内容

可以复用或参考：

- `sdk/python/src/codex_app_server/generated/v2_all.py`
- `sdk/python/src/codex_app_server/generated/notification_registry.py`
- `sdk/python/src/codex_app_server/client.py`
- `codex-rs/app-server-test-client/src/lib.rs`

## 9.3 `CodexEventReducer`

建议位置：

- 可先做成 `CodexManagedSessionService` 的私有方法
- 若后续复杂，再独立为 `codex_event_reducer.py`

职责：

- 消费 JSON-RPC notification
- 维护 managed session 内存状态
- 将用户可读输出投喂给 `LiveOutputService`

phase1 最少关心：

- `thread/started`
- `thread/status/changed`
- `turn/started`
- `item/agentMessage/delta`
- `turn/completed`
- `item/commandExecution/outputDelta`
- `item/fileChange/outputDelta`
- `error`

## 9.4 `LiveOutputService` 扩展

当前 `LiveOutputService` 主要处理 recent window。

phase1 需要增加：

- `active_text`
- `session_mode`
- `thread_id`
- `turn_id`
- `thread_status_type`
- `thread_active_flags`
- `last_error`

这样 `/live/state.json` 才能同时满足：

- 输出展示
- 会话状态显示
- 输入区 enable / disable 判断

## 9.5 `SessionService` 扩展

建议补充：

- `codex_session_mode`
- `codex_thread_id`
- `codex_active_turn_id`
- `codex_thread_status_type`
- `codex_thread_active_flags`
- `codex_can_send`
- `codex_can_interrupt`
- `codex_last_error`

## 10. API 设计

phase1 不改 observation token 体系，只新增 live session 读写接口。

## 10.1 读接口

继续使用：

- `GET /live/state.json?token=...`

返回中新增：

```json
{
  "output": {
    "session_mode": "managed",
    "thread_id": "thr_123",
    "turn_id": "turn_456",
    "thread_status_type": "active",
    "thread_active_flags": [],
    "can_send": true,
    "can_interrupt": true,
    "active_text": "正在生成中的文本",
    "latest_text": "当前显示文本"
  }
}
```

## 10.2 写接口

新增：

- `POST /live/session/message?token=...`
- `POST /live/session/interrupt?token=...`

请求示例：

```json
{
  "message": "继续往下翻"
}
```

响应示例：

```json
{
  "ok": true,
  "mode": "managed",
  "thread_id": "thr_123",
  "turn_id": "turn_456",
  "dispatched_as": "turn_steer"
}
```

## 10.3 token 策略

phase1 可以先复用 observation token，减少改动。

但文档必须明确：

- phase1.5 建议拆分为 `view token` 与 `control token`

否则 live 链接泄露就相当于泄露控制权。

## 11. live 页面改动

页面不重做，只在当前 `Codex Output` 卡片下增加输入区。

## 11.1 UI 增量

新增区域：

- session 模式 badge：`Readonly Attach` / `Managed`
- 输入框
- `Send` 按钮
- `Interrupt` 按钮
- 错误提示行

## 11.2 页面行为

- 每秒继续轮询 `/live/state.json`
- `Send` 点击后发 `POST /live/session/message`
- 成功后清空输入框
- 若 `can_send == false`，按钮置灰
- 若 `can_interrupt == false`，interrupt 按钮置灰

## 11.3 展示文案建议

- `attach_readonly`：Watching existing local Codex session
- `managed`：Controlling managed local Codex session
- `waitingOnApproval`：Managed session requires approval; unsupported in live v1
- `waitingOnUserInput`：Codex is waiting for user input

## 12. 事件映射规则

## 12.1 输出主轨

### `item/agentMessage/delta`

- 追加到 `active_text`
- `status = running`
- 更新时间 heartbeat

### `turn/completed`

- 将 `active_text` 或 turn final text 提交到 recent
- 清空 `active_text`
- `status = idle`
- `active_turn_id = null`

## 12.2 状态轨

### `thread/started`

- 设置 `mode = managed`
- 写入 `thread_id`
- 更新 thread status

### `thread/status/changed`

- 更新：
  - `thread_status_type`
  - `thread_active_flags`
  - `can_send`
  - `can_interrupt`

映射建议：

- `idle` -> `can_send=true`, `can_interrupt=false`
- `active` -> `can_send=true`, `can_interrupt=true`
- `notLoaded` -> `can_send=false`, `can_interrupt=false`
- `systemError` -> `can_send=false`, `can_interrupt=false`

### `turn/started`

- `active_turn_id = turn.id`
- `status = running`

## 12.3 activity 副轨

### `item/commandExecution/outputDelta`

phase1 不展示原始输出全文，只做：

- heartbeat 更新
- 可选 recent 中追加一条短 meta，如 `Running shell command...`

### `item/fileChange/outputDelta`

同样只做 heartbeat 或短 meta。

## 13. 状态机

phase1 建议使用以下最小状态机：

### 13.1 session mode

- `none`
- `attach_readonly`
- `managed`

### 13.2 thread status

- `idle`
- `active`
- `waiting_on_approval`
- `waiting_on_user_input`
- `system_error`
- `not_loaded`

其中：

- `waiting_on_approval`
  - 来自 `thread/status/changed.type == active`
  - 且 `activeFlags` 包含 `waitingOnApproval`
- `waiting_on_user_input`
  - 来自 `activeFlags` 包含 `waitingOnUserInput`

页面展示可以更友好，但内部建议保持与协议接近。

## 14. phase1 的实现步骤

## 14.1 Step 1: 扩展状态模型

修改：

- `SessionService`
- `LiveOutputService`
- `/live/state.json` 输出结构

目标：

- 页面先能看到 managed session 的基础状态位

## 14.2 Step 2: 实现 `CodexAppServerTransport`

完成：

- 子进程启动
- initialize
- request/response 分发
- notification callback
- 优雅关闭

## 14.3 Step 3: 实现 `CodexManagedSessionService`

完成：

- `send_message(message)`
- `interrupt()`
- `resume_or_start()`
- `on_notification(...)`

## 14.4 Step 4: 接入现有 registry / app 生命周期

修改：

- `src/agent_computer/services/registry.py`
- `src/agent_computer/api/app.py`

原则：

- daemon 启动时不强制立刻拉起 managed session
- 第一次发送消息时 lazy start

## 14.5 Step 5: 新增路由

新增：

- `routes_live_session.py`

接口：

- `POST /live/session/message`
- `POST /live/session/interrupt`
- 可选 `GET /internal/live-session`

## 14.6 Step 6: live 页面加输入区

修改：

- `src/agent_computer/api/live_page.py`

要求：

- 不引入构建系统
- 继续原生 JS
- 保持当前视觉风格

## 14.7 Step 7: 兼容 attach takeover

实现：

- watcher 已发现 session id 时，优先 `thread/resume`
- resume 失败再 `thread/start`

## 15. 测试计划

## 15.1 单元测试

新增测试建议：

- `LiveOutputService` 处理 `active_text -> recent` 提交
- `CodexManagedSessionService` 路由消息到 `turn/start` / `turn/steer`
- `thread/status/changed` 到页面状态映射
- `interrupt()` 清理 `active_turn_id`

## 15.2 集成测试

至少覆盖：

1. 首次发送消息
   - 创建 thread
   - 创建 turn
   - 输出最终可见
2. 恢复已有 thread
   - `thread/resume`
   - 新 turn 正常执行
3. 运行中 steer
   - active turn 存在
   - 第二条输入走 `turn/steer`
4. interrupt
   - 当前 turn 被中断
   - 状态回到 idle / interrupted

## 15.3 手工验证

手工验收步骤：

1. 启动 daemon
2. 打开 `/live`
3. 确认 screen 和 output 正常
4. 在输入框发送一条消息
5. 看到输出持续更新
6. 运行中再次发送消息
7. 确认走 steer，不新开 thread
8. 点击 interrupt
9. 确认当前 turn 停止

## 16. 风险与对策

### 16.1 风险：app-server transport 读写竞争

对策：

- 明确使用单 reader thread
- HTTP handler 不直接读 stdout

### 16.2 风险：resume 到的 thread 与当前本地 terminal session 不一致

对策：

- takeover 只基于当前仓库 cwd 过滤
- 页面展示当前 `thread_id`
- phase1 不承诺“接管任意前台窗口里的 Codex”

### 16.3 风险：审批流卡死

对策：

- phase1 默认 `approvalPolicy="never"`
- 或收到 approval 时明确报错并停止 managed turn

### 16.4 风险：live token 泄露带来控制风险

对策：

- phase1 文档明确这是临时方案
- phase1.5 拆 control token

## 17. 成功标准

满足以下几点即视为 phase1 成功：

1. `/live` 页面可实时看到比当前更完整的 managed Codex 输出
2. `/live` 页面可直接给当前 managed Codex session 发消息
3. 运行中追加消息能走 `turn/steer`
4. 可中断当前 turn
5. 不依赖前台 terminal window
6. 不依赖 GUI 注入
7. 保留现有 attach_readonly 作为回退路径

## 18. 一句话总结

phase1 不做 terminal 接管，而是在现有 live + watcher 架构上，新增一个基于 Codex 官方 `app-server` 的轻量托管层，把 `live 输入 -> thread/turn 协议 -> notification 输出 -> LiveOutputService` 这条链路打通，以最小代价实现“能看、能发、能中断”的本地 Codex session 管理能力。
