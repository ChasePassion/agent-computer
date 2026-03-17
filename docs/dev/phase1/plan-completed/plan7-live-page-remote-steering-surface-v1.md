# Plan 7: Live 页面重构为 Remote Steering Surface v1

状态：active
创建日期：2026-03-17

## 1. 背景

当前项目已经完成过两轮 live 能力演进：

- Plan 5：`/live` 从只看屏幕升级为“看屏幕 + 看 Codex output”
- Plan 6：`/live` 增加 managed Codex session，支持直接 message / interrupt

这两步在技术上证明了两件事：

1. 手机端看桌面最新画面是成立的
2. 手机上的 live 页面可以承担一部分远程控制职责

但 Plan 6 的核心建模方向需要整体推翻。

当前 `live` 页面把控制对象定义为：

- 一个 daemon 托管的 `managed Codex session`

这带来了几类根本问题：

1. **系统边界错位**
   - 用户真正想远程操控的是“本地 Codex 窗口所代表的工作流”
   - 不是让 `agent-computer` 在后台再包一层 Codex runtime
2. **概念过重**
   - `session_mode`
   - `thread_id`
   - `turn_id`
   - `can_send`
   - `can_interrupt`
   - `attach_readonly`
   - `managed`
   这些概念把 `live` 页变成了一个半成品 app-server client，而不是一个高效的远程 steering 面板
3. **页面职责漂移**
   - live 页面原本是 observation layer 的一部分
   - 现在却承担了 session orchestration、thread state、interrupt 协议等职责
4. **实现维护成本高**
   - 需要维护 `codex app-server`
   - 需要维护 transport、notification reducer、watcher、managed session 恢复逻辑
   - 还要同时兼容 attach-readonly 和 managed 两条路径

这与当前产品意图不一致。

当前产品真正需要的是：

**把 `/live` 页面重构成一个最小远程 steering surface。**

也就是：

- 远程看当前桌面
- 远程把鼠标移动到 Codex 窗口
- 远程点击 Codex 输入框或其它必要位置
- 远程写入消息
- 远程触发 `Ctrl+V`
- 可选触发 `Enter`
- 继续通过 live 画面观察 Codex 窗口的实时变化

这更接近“用手机扶正本地 Codex 窗口，然后让 Codex 继续操控电脑”，而不是“用 live 页面重做一个新的 Codex 客户端”。

## 2. 新产品定义

本次重构后的 `/live` 产品定义如下：

### 2.1 页面定位

`/live` 是：

- 一个远程 observation 页面
- 一个最小可控的 desktop steering surface

`/live` 不是：

- Codex session manager
- Codex app-server client
- terminal emulator
- approval UI
- thread/turn orchestration dashboard

### 2.2 控制目标

控制对象从：

- `Codex thread / turn`

改为：

- `Windows desktop absolute coordinates`
- `foreground Codex window`
- `clipboard paste + keyboard actions`

### 2.3 用户闭环

重构后的最小闭环应该是：

1. 用户在手机端打开 `/live`
2. 用户在 live 画面上点击目标区域
3. 系统把浏览器内点击坐标映射成桌面绝对坐标
4. daemon 执行 `move` / `click`
5. 用户在页面输入消息
6. 系统执行 `paste` 或 `Ctrl+V`
7. 用户视情况再触发 `Enter`
8. `Codex` 窗口开始输出
9. live 屏幕持续刷新，用户观察结果

## 3. 本次重构的核心结论

### 3.1 不做兼容迁移

本次不是“在旧架构旁边再加一个新按钮”。

本次是：

**彻底删除 live-managed-session 方案。**

所有与下面这些概念直接相关的 live 写路径，都应移除：

- `managed session`
- `attach_readonly`
- `thread/start`
- `thread/resume`
- `turn/start`
- `turn/steer`
- `turn/interrupt`
- `/live/session/message`
- `/live/session/interrupt`

### 3.2 `/live` 只保留桌面控制语义

新的 `/live` 写路径只允许表达这些桌面原子动作：

- `move`
- `click`
- `double click`
- `scroll`
- `paste`
- `press`
- `hotkey`

页面上的“给 Codex 发消息”不再是一个 session-level API，而是一个动作编排结果。

语义从：

- “发送消息到当前 Codex turn”

改为：

- “把文本贴到当前前台 Codex 输入框”
- “可选再按 Enter”

### 3.3 live 页面默认只看屏幕，不再承担 Codex transcript 的强依赖

Plan 5 和 Plan 6 把 `/live` 做成了“屏幕 + transcript + session state”的双栏页。

本次重构后，产品中心应该回到 screen live。

Codex transcript、recent activity、plan、reasoning 这些展示能力全部重新评估，不做兼容保留假设。

默认结论：

- **可以整体删除 live 页中的 Codex output 面板**
- 如果未来需要文本态势感知，应另做独立只读面板，而不是继续绑定 managed session 架构

## 4. phase1 重构范围

## 4.1 要做

- 把 `/live` 页面重构为 screen-first 的远程 steering 单页
- 支持点击 screen 图像后换算为桌面坐标
- 新增 live 专用控制接口
- 在页面中增加消息输入框和动作按钮
- 支持 `move` / `click` / `double click`
- 支持 `paste`
- 支持 `Ctrl+V`
- 支持 `Enter`
- 支持“Paste Only”和“Paste + Enter”两类动作
- 保持现有 observation 刷新链路
- 更新测试和文档

## 4.2 不做

- 兼容旧的 `/live/session/*` 行为
- 保留 `managed session` 作为可选模式
- 保留 `attach_readonly` 作为 live 页模式
- 保留 live transcript 展示的现有 UI 结构
- 在本次重构里引入 WebSocket
- 做完整远程桌面协议
- 做移动端虚拟鼠标手势层

## 5. 需要整体删除的旧能力

这部分是本计划最重要的地方：**删除目标必须一次性定义清楚。**

## 5.1 直接删除的 API

以下 API 在新模型下不再成立：

- `POST /live/session/message`
- `POST /live/session/interrupt`

对应文件：

- `src/agent_computer/api/routes_live_session.py`

处理原则：

1. 删除路由实现
2. 从 `app.py` 注销 live session router
3. 删除相关 request model
4. 删除相关测试

## 5.2 直接删除的 live 页面交互

以下 live 页面元素和脚本逻辑不再成立：

- `Send` 按钮
- `Interrupt` 按钮
- `session_mode` pill
- `output_status` pill 中与 managed thread 状态耦合的部分
- `composer-hint` 中“take over current local Codex thread”的文案
- 发送消息表单提交到 `/live/session/message`
- interrupt 调用 `/live/session/interrupt`

对应文件：

- `src/agent_computer/api/live_page.py`

处理原则：

1. 删除现有 Codex Live 区域
2. 重新设计为 Control 区域
3. 页面状态模型从 `output + session` 改为 `screen + control`

## 5.3 直接删除的服务层能力

以下服务不再属于 phase1 产品边界，应整体移除：

- `CodexManagedSessionService`
- `CodexAppServerTransport`
- `CodexSessionWatcher`
- `LiveOutputService`

对应文件：

- `src/agent_computer/services/codex_managed_session_service.py`
- `src/agent_computer/services/codex_app_server_transport.py`
- `src/agent_computer/services/codex_session_watcher.py`
- `src/agent_computer/services/live_output_service.py`

以及：

- `src/agent_computer/services/__init__.py`
- `src/agent_computer/services/registry.py`
- `src/agent_computer/api/routes_live_output.py`
- `src/agent_computer/api/app.py`
- `src/agent_computer/services/session_service.py` 中 live output 相关状态

删除原则：

1. 不保留占位空壳
2. 不做 deprecated 包装
3. 不保留“以后也许还用”的协议层
4. 以当前产品模型为准，彻底清理未使用路径

## 5.4 直接删除的测试

以下测试在新模型下整体失效，应删除或整体重写：

- `tests/test_live_output_and_managed_session.py`

如果该测试文件里混有少量仍然成立的行为断言，则拆出后保留，其余全部删除。

## 6. 新架构

重构后的 phase1 架构应收敛为：

```text
mobile browser
  ->
/live
  ->
token-protected live control endpoints
  ->
ActionService
  ->
pyautogui / clipboard / keyboard
  ->
foreground Codex window
  ->
desktop changes
  ->
ObservationService latest frame
  ->
/live/frame.jpg + /live/state.json
  ->
mobile browser
```

关键点：

1. live 页面只负责控制桌面
2. daemon 不再管理 Codex 会话协议
3. 用户通过看屏幕结果确认动作是否生效

## 7. 新接口设计

## 7.1 为什么不直接让 `/live` 调用 `/actions/*`

虽然现有 `/actions/*` 已经能执行动作，但 live 页面直接调用它们有两个问题：

1. `/actions/*` 当前不是围绕 observation token 设计的
2. `live` 页需要更清晰的权限边界和更稳定的前端契约

因此推荐新增一组 live 专用控制路由。

## 7.2 新增 live control API

建议新增：

- `POST /live/control/move`
- `POST /live/control/click`
- `POST /live/control/scroll`
- `POST /live/control/paste`
- `POST /live/control/press`
- `POST /live/control/hotkey`

这些接口的共同特点：

1. 必须校验 observation token
2. 内部调用现有 `ActionService`
3. 返回统一的轻量动作结果
4. 失败时返回简洁错误，不暴露无关内部状态

### 7.2.1 坐标语义

`move` 和 `click` 只接受：

- 桌面绝对坐标

前端负责把 `<img>` 内部点击点换算为原始 screen 坐标。

这样后端保持简单，避免重复维护 DOM 映射逻辑。

### 7.2.2 组合动作

本次不新增复杂的 server-side macro runner。

页面先用原子动作组合：

- `Paste Only`
- `Paste + Enter`
- `Ctrl+V`

如果后续确实需要，再加 `POST /live/control/paste-and-enter` 这种语义化动作。

phase1 默认保持原子接口优先。

## 8. live 页面重构方案

## 8.1 页面结构

新的 `/live` 页面建议只有两块主区：

1. `Screen Live`
2. `Remote Control`

### 8.1.1 Screen Live

保留：

- `preview / grid` 切换
- 最新更新时间
- 分辨率
- 鼠标当前位置
- 屏幕图像刷新

新增：

- 点击图像时显示当前选中的桌面坐标
- 可选显示最近一次控制动作结果

### 8.1.2 Remote Control

包含：

- 当前选中坐标展示
- `Move`
- `Click`
- `Double Click`
- `Scroll Up`
- `Scroll Down`
- 文本输入框
- `Paste`
- `Paste + Enter`
- `Ctrl+V`
- `Enter`

## 8.2 交互细节

### 8.2.1 点击屏幕图像

点击 `<img>` 后：

1. 读取图片在浏览器中的显示尺寸
2. 结合最新 `frame.json` 的原始宽高
3. 计算缩放比
4. 把点击点换算为原始桌面坐标
5. 在 UI 中更新“selected point”

### 8.2.2 move / click 执行

建议默认不做“点图即点击”。

phase1 采用：

1. 用户先点图选位置
2. 再点击 `Move` 或 `Click`

原因：

1. 手机端误触概率高
2. 直播帧存在刷新延迟
3. 显式两步更容易理解和纠错

### 8.2.3 发消息给 Codex

新的“给 Codex 发消息”流程变为：

1. 用户先把 Codex 输入框点成前台焦点
2. 在 live 页输入文本
3. 点击 `Paste`
4. 如要真正提交，再点击 `Enter`
5. 或直接点击 `Paste + Enter`

这条路径不再关心：

- thread 是否存在
- turn 是否运行中
- 是否应该 steer
- interrupt 是否可用

这些都不再是 `agent-computer` 的职责。

## 8.3 页面状态精简

删除下面这些状态：

- `lastOutputSeq`
- `submittingMessage`
- `interruptingTurn`
- `outputStatusPill`
- `sessionModePill`
- `sessionLine`
- `terminalNote`
- `terminalBody`
- `messageError` 中与 managed-session 响应相关的部分

新增下面这些状态：

- `selectedPoint`
- `controlBusy`
- `lastControlAction`
- `lastControlError`

## 9. 服务层改造计划

## 9.1 Registry 收缩

`ServiceRegistry` 应收缩回 observation/control 核心：

- `session`
- `capture`
- `actions`
- `observation`
- `browser_assist`
- `navigation`

移除：

- `live_output`
- `codex_session_watcher`
- `codex_managed_session`

## 9.2 SessionService 收缩

`SessionService` 中与 live output / codex session 状态相关的字段应移除，例如：

- `live_output`
- `live_output_status`
- `live_output_updated_at`
- `live_output_heartbeat_at`
- `live_output_seq`
- `live_output_session_id`
- `live_output_source_rollout_path`
- `codex_session_mode`
- `codex_thread_id`
- `codex_active_turn_id`
- `codex_thread_status_type`
- `codex_thread_active_flags`
- `codex_can_send`
- `codex_can_interrupt`
- `codex_last_error`

保留 screen / browser assist / system health 相关状态。

## 9.3 app 装配收缩

`src/agent_computer/api/app.py` 中应移除：

- `routes_live_output`
- `routes_live_session`
- 启动和关闭时对 `codex_session_watcher`、`codex_managed_session` 的管理

新增：

- `routes_live_control`

## 10. 测试计划

## 10.1 删除或重写的测试

删除：

- `tests/test_live_output_and_managed_session.py`

重写 live 页相关测试，使其覆盖：

- `/live` 页面不再包含 `Send` / `Interrupt`
- `/live` 页面包含新的 control 区
- `/live/control/*` 需要 token
- `move` / `click` / `paste` / `press` 正常转发到 `ActionService`
- 错误参数会返回合理错误

## 10.2 新增测试点

应新增以下测试：

1. 图像模式切换仍然正常
2. live 页面 HTML 包含 selected-point 和 control buttons
3. live control 路由 token 校验正确
4. `paste + enter` 前端触发的动作顺序正确
5. 删除 managed session 相关服务后，应用仍可正常启动

## 11. 文档更新计划

以下文档必须同步更新：

- `README.md`
- `docs/dev/phase1/plan-completed/plan5-live-page-screen-plus-output-v1.md`
- `docs/dev/phase1/plan-completed/plan6-live-page-managed-codex-session-v1.md`

处理方式：

1. `README.md` 更新为新事实
2. 旧 plan 文档不删除，但应视为历史方案
3. 在实现完成后，把本计划从 `plan-avtive` 移到 `plan-completed`

README 里应明确写出：

- `/live` 现在是 remote steering surface
- live 页面不再直接接管 Codex session
- 给 Codex 发消息的方式是“点到输入框 + paste / enter”

## 12. 分阶段执行顺序

为了避免一边删一边炸，重构顺序必须固定：

### 阶段 1：页面和 API 新模型成型

1. 新增 `routes_live_control.py`
2. 重构 `live_page.py`
3. 让新页面先可以通过 live control 执行动作

### 阶段 2：删旧 live session / live output 路径

1. 删除 `routes_live_session.py`
2. 删除 `routes_live_output.py`
3. 从 `app.py` 去掉相关 router

### 阶段 3：删服务层

1. 删除 `CodexManagedSessionService`
2. 删除 `CodexAppServerTransport`
3. 删除 `CodexSessionWatcher`
4. 删除 `LiveOutputService`
5. 更新 `registry.py` 和 `session_service.py`

### 阶段 4：删测试和文档收尾

1. 删除旧测试
2. 增加新测试
3. 更新 README

## 13. 成功标准

重构完成后，应满足以下标准：

1. 打开 `/live` 可以持续看到桌面最新画面
2. 手机端点击画面可选定桌面坐标
3. 可以通过 live 页执行 `move` / `click`
4. 可以通过 live 页把文本 paste 到本地 Codex 输入框
5. 可以通过 live 页触发 `Enter`
6. live 页面中不再存在 managed session / interrupt / thread status 概念
7. 代码库中不再保留 live-managed-session 主链路及其测试

## 14. 风险与注意事项

### 14.1 焦点风险

新模型要求：

- 前台焦点确实在 Codex 窗口或目标输入框

否则 `paste` / `enter` 会作用到错误窗口。

这是该模型的天然约束，不是 bug。页面文案需要明确提示。

### 14.2 直播延迟风险

live 画面存在采样和轮询延迟，因此：

- 不应默认“点图即点击”
- 应保留“先选点，再执行”的两步模型

### 14.3 剪贴板副作用

`paste` 当前依赖系统剪贴板。

需要在文档中说明：

- 可选 `restore_clipboard`
- 默认行为可能会覆盖当前剪贴板内容

### 14.4 完全删除旧模型的影响

本计划明确接受以下影响：

1. 失去 API 级 `interrupt`
2. 失去 daemon 级 thread / turn 语义
3. 失去 live transcript 展示

这些都属于主动产品收缩，不视为回归。

## 15. 一句话结论

Plan 7 的本质不是“给 live 页再加几个按钮”，而是：

**彻底放弃 live 页作为 Codex session manager 的方向，把它重构为一个最小、直接、稳定的远程 steering surface。**
