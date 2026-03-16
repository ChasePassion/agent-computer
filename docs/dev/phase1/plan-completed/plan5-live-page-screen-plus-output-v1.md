# Plan 5: Live 页面增加 Codex Output v1

状态：active
创建日期：2026-03-14

## 1. 背景

当前项目已经有一套可用的 observation layer：

- `GET /live?token=...` 提供手机可访问的 live 页面
- `ObservationService` 持续产出 `preview` / `grid` 两份 latest frame
- `SessionService` 在内存里保存最新 screen 状态摘要

但现在的 live 页面只解决了“看动作”，没有解决“看解释”。

因此手机端仍然有 3 个真实缺口：

1. 只能看到屏幕变化，无法知道 Codex 为什么这么做
2. Codex 正在输出什么，手机端不可见
3. 无法快速判断它是在推进、空闲，还是疑似卡住

这次增强的目标不是做一个新产品，而是在现有 `/live` 页面内，把它从：

- 只看屏幕

升级为：

- 看屏幕
- 看 Codex 输出
- 看当前进度状态

## 2. 现状评估

结合当前代码，现状非常明确：

### 2.1 live 页面当前实现很轻

`src/agent_computer/api/routes_observation.py` 里直接内嵌了一段 HTML。

页面行为是：

1. 打开 `/live`
2. 每 1 秒轮询 `/live/frame.json`
3. 若 `frame_seq` 变化，则刷新图片

这说明：

- v1 继续走“单页 + 轮询”是合理的
- 不需要引入新的前端工程或构建系统

### 2.2 屏幕数据链路已经完整

`src/agent_computer/services/observation_service.py` 已经完成：

- 后台抓屏
- `preview` / `grid` latest 文件原子替换
- latest meta 生成
- Session 内存摘要更新

所以屏幕半边不用重做，只需要继续复用。

### 2.3 当前 `agent-computer` 没有接入 Codex 输出数据源，但本机 Codex CLI 已经有可利用的数据源

这是这次方案最关键的事实。

目前 `agent-computer` 自己只知道：

- screen frame
- browser assist 状态
- system health

但通过社区资料、官方文档和本机核对，可以确认本机 `codex` 已经暴露了两个可用入口：

1. `codex exec --json`
   - 官方 non-interactive 文档说明该模式会把事件以 JSONL 打到 `stdout`
2. `%USERPROFILE%\\.codex\\sessions\\YYYY\\MM\\DD\\rollout-*.jsonl`
   - 社区已经有工具直接解析这些 session 文件
   - 本机也已确认该目录存在，而且 2026-03-14 仍在持续生成新文件

本机核对结果：

- `codex` 来自 npm 全局安装：`C:\\Users\\...\\AppData\\Roaming\\npm\\codex.cmd`
- 当前版本：`codex-cli 0.114.0`
- 本机存在 `C:\\Users\\...\\.codex\\sessions\\2026\\03\\14\\rollout-*.jsonl`

也就是说：

**单改 live 页前端仍然没有意义，但 v1 不一定非要先改 Codex runtime。更现实的第一步是直接从本机 Codex 产物采集。**

`agent-computer` 需要新增的是：

- 本机 session watcher
- 或受控启动时的 stdout JSON watcher

而不是从零发明一套 terminal 抓取方案。

## 3. v1 产品边界

这次增强只负责：

- 在现有 `/live` 页面显示 screen + Codex output
- 让手机端知道“刚刚输出了什么”
- 给出一个足够轻量的当前状态感知

v1 明确不做：

- 终端输入框
- 远程控制 Codex
- 完整 terminal emulator
- 全量历史日志系统
- 多会话切换
- 搜索 / 过滤 / 下载日志

## 3.1 优化后的 phase1 范围收缩

基于 2026-03-14 的官方文档、社区讨论和本机日志核对，phase1 应进一步收缩：

1. **先做 attach，不做 orchestrate**
   - phase1 不接管 Codex 启动
   - phase1 只附着到本机已有的 `~/.codex/sessions/.../rollout-*.jsonl`
2. **先做只读链路，不把写入链路当主路径**
   - phase1 主链路是 watcher 读 session
   - internal ingest API 和 `live-output` CLI 退到 fallback / phase1.5
3. **先做 commentary + final，可读优先**
   - phase1 只解析能直接给手机读的文本
   - 不把 `function_call_output` 原文塞进输出区
4. **先保证当前仓库正确 attach**
   - 必须用 `session_meta.payload.cwd` 过滤出当前仓库对应的 rollout 文件
   - 不做多仓库混读

这样 phase1 更轻，也更符合你现在“Codex 已经在本机跑起来”的事实。

## 4. 核心设计决策

### 4.1 输出源选择：优先采集本机 session / JSON 事件，不抓原始终端字节流

v1 推荐优先级：

1. 本机 session 文件：`%USERPROFILE%\\.codex\\sessions\\...\\rollout-*.jsonl`
2. 受控启动时：`codex exec --json`
3. 可选 fallback：本地 ingest API / CLI 手动写入摘要

不推荐做：

- Win32 终端窗口文本抓取
- PTY 全量镜像
- OCR 识别终端截图
- 浏览器里嵌 xterm.js 做完整终端

原因：

1. 产品目标是“可读”，不是“还原终端”
2. 原始终端字节流噪音太大，不适合手机阅读
3. `codex` 本机已经有 session JSONL 和 JSON stdout，两者都比抓 terminal 稳定
4. 结构化输出更容易做状态判断和最近窗口裁剪

结论：

**v1 应优先读取 Codex 本机已有的结构化产物，而不是在桌面层抓终端。**

### 4.2 传输模型选择：Local Session / JSON Stream -> Daemon -> Live 页面

推荐链路：

```text
Codex local session file
or codex exec --json stdout
    ->
CodexSessionWatcher
    ->
LiveOutputService
    ->
Session + snapshot
    ->
/live 页面轮询读取
```

这样做的原因：

1. `/live` 页面只关心“可显示状态”，不直接耦合 Codex UI
2. daemon 统一承接 screen 和 output 两类状态
3. 后续 `/system/health`、脚本、CLI 都可以复用这份 output 摘要

### 4.2.1 优化后的主路径：Attach Mode

phase1 明确采用：

```text
existing Codex process
  ->
~/.codex/sessions/.../rollout-*.jsonl
  ->
CodexSessionWatcher
  ->
LiveOutputService
  ->
/live/state.json
  ->
/live
```

这条路径的优点是：

1. 不改变你现在使用 Codex 的方式
2. 不要求 live 功能去包裹或代理 Codex 启动
3. 能先最小代价验证“手机同时看屏幕和输出”是否成立

`codex exec --json` 保留为 phase1.5 的增强路径，而不是 phase1 前提。

### 4.3 刷新模型选择：继续使用轮询，不上 WebSocket

当前 screen 已经是轮询模型。

v1 输出继续使用轮询，保持同一套节奏：

- 每 `1000ms` 拉取 live state
- screen 和 output 一起更新

不做 WebSocket 的原因：

1. 现有 live 页已经是 poll-based
2. v1 重点是可见性，不是高频流式日志
3. 移动端网络下，1 秒级轮询已经够用
4. 实现成本和调试成本都更低

### 4.4 数据保留选择：只保留最近窗口

v1 不做全量历史。

只保留：

- 最新状态
- 最近一小段可读输出窗口

建议默认值：

- 最近 `12` 条输出项
- 总字符数上限 `6000`

超过上限时：

- 从最旧内容开始裁剪
- 页面只显示最近窗口

这与产品目标一致：

- 先看最新
- 先解决“现在什么情况”
- 不是先做日志平台

### 4.5 状态模型选择：简化成少量状态

API 输出状态建议只保留：

- `running`
- `idle`
- `no_output`

页面层再根据时间差给出提示：

- `running` 且 `updated_at` 超过阈值未变化：显示“可能卡住”

这样可以保持 v1 模型简单，同时满足“知道它是不是还在推进”的产品目标。

### 4.6 事件选择：只解析高价值事件，避免重复与噪音

结合本机 session JSONL 实际内容，phase1 推荐只关心下面几类：

1. `event_msg.payload.type == "task_started"`
   - 作为新 turn 开始
   - 触发 output window reset
   - 状态切到 `running`
2. `event_msg.payload.type == "agent_message"`
   - 直接取 `payload.message`
   - 作为 commentary 文本主来源
3. `event_msg.payload.type == "task_complete"`
   - 取 `payload.last_agent_message`
   - 作为 final 文本主来源
   - 状态切到 `idle`
4. `response_item.payload.type == "function_call"` / `"function_call_output"`
   - 只更新 activity heartbeat
   - 默认不直接展示原文

phase1 默认忽略：

- `reasoning`
- `token_count`
- `user_message`
- 大段 `function_call_output` 原始内容
- `response_item.role=assistant` 与 `event_msg.agent_message` 重复的部分

这样可以同时解决两件事：

1. 输出区足够干净，可读
2. 状态判断不至于因为“没有新 commentary”就误判卡住

## 5. 推荐总体架构

## 5.1 组件拆分

建议新增 4 个部分：

1. `LiveOutputService`
2. `CodexSessionWatcher`
3. `live 页面 output UI`
4. `live output CLI`（fallback）

职责如下。

### A. Output Producer

位置：

- v1 主路径不再强依赖 runtime / wrapper
- 优先直接读取本机 `codex` 已写出的 session / stdout 事件

职责：

- 从 session JSONL 中提取用户可读输出
- 或在受控启动模式下解析 `codex exec --json`
- 将结果交给 `LiveOutputService`

### B. LiveOutputService

位置：

- `src/agent_computer/services/live_output_service.py`

职责：

1. 接收 output event
2. 维护 recent window
3. 维护当前状态
4. 生成对前端友好的 snapshot
5. 将 snapshot 原子写盘，便于 daemon 重启后恢复

### C. CodexSessionWatcher

位置建议：

- `src/agent_computer/services/codex_session_watcher.py`

职责：

1. 找到最新的 `rollout-*.jsonl`
2. 持续 tail 新增行
3. 解析感兴趣的 event 类型
4. 映射成 `LiveOutputService` 的 recent window
5. 只接入 `session_meta.payload.cwd == E:\\code\\agent-computer` 的 session
6. 当发现更新更晚的新 rollout 文件时，自动切换 attach 目标
7. 切换到新文件时，从头读取该文件一次，避免漏掉 turn 开头的 commentary

### D. Public Read API

位置建议：

- 继续放在 `routes_observation.py`

职责：

- 让 `/live` 页面读取 output 状态
- 让手机端只用现有 token 访问

### E. Internal Ingest API（可选 fallback）

位置建议：

- 新增 `src/agent_computer/api/routes_live_output.py`

职责：

- 只在 session watcher 不可用，或后续需要受控启动时使用
- 作为测试和手工注入的补充入口

将 public read 和 internal write 拆开，是为了避免把内部写接口和公网 live 页面混在一起。

## 5.2 数据流

推荐数据流如下：

```text
Codex rollout-*.jsonl
  -> CodexSessionWatcher tail
  -> parse response_item / event_msg / other useful events
  -> LiveOutputService.append_event(...)
  -> SessionService.set_live_output(...)
  -> artifacts/live-output/latest.json
  -> GET /live/state.json?token=...
  -> /live 页面更新 output 区
```

受控启动备选链路：

```text
agent wrapper
  -> codex exec --json
  -> stdout parser
  -> LiveOutputService.append_event(...)
```

## 5.3 为什么推荐 session tail 作为第一阶段，而不是先改 runtime

推荐优先级：

1. session JSONL tail
2. `codex exec --json`
3. `CLI -> daemon API`

原因：

1. 你当前就是 npm 本机安装，session 文件已经存在，不必先接管 Codex 启动方式
2. attach 到现有 Codex 使用习惯，侵入性最低
3. 由 service 统一负责裁剪、持久化、状态计算
4. `exec --json` 仍然很有价值，但它更适合“由我们自己启动 Codex”的场景
5. 社区已经有现成实践直接消费 session 文件，这条路工程风险更低

内部 API / CLI 写入可以作为 fallback，但不建议作为主路径。

## 5.4 优化后的 phase1 目标

phase1 不追求“最通用”，而追求“最快验证有效”。

因此目标压缩为：

1. 只支持本机 Codex
2. 只支持当前仓库 `E:\\code\\agent-computer`
3. 只支持单活跃会话
4. 只显示 commentary / final / 状态 / 更新时间
5. 只在 `/live` 页面消费，不先扩展出一套独立控制台

这是一个刻意收窄的实现范围，不是能力不足，而是为了把最值钱的路径先做稳。

## 6. 输出数据模型

## 6.0 本机已验证的 session 事件形状

在本机 `C:\\Users\\...\\.codex\\sessions\\...\\rollout-*.jsonl` 中，已确认存在并可利用的结构包括：

### session_meta

用于识别仓库：

```json
{
  "type": "session_meta",
  "payload": {
    "id": "019ceba7-388c-7273-8e70-9f611b919255",
    "cwd": "E:\\code\\agent-computer"
  }
}
```

### commentary

可直接给手机端展示：

```json
{
  "type": "event_msg",
  "payload": {
    "type": "agent_message",
    "message": "我会先检查这个项目里现成的浏览器/桌面自动化能力和已有登录状态。",
    "phase": "commentary"
  }
}
```

### final

可直接作为 turn 结束摘要：

```json
{
  "type": "event_msg",
  "payload": {
    "type": "task_complete",
    "last_agent_message": "技术实现方案已经写到 ..."
  }
}
```

这说明 phase1 不需要自己从终端文本里二次抽取语义，直接消费这些事件就够了。

## 6.1 事件模型

Producer 发给 daemon 的最小 event 结构建议如下：

```json
{
  "session_id": "active",
  "kind": "commentary",
  "text": "我会先确认 live 页当前实现和数据流。",
  "status": "running",
  "created_at": "2026-03-14T19:30:00+08:00"
}
```

字段定义：

- `session_id`
  - v1 固定单会话，可先统一写 `active`
- `kind`
  - `commentary | final | tool`
- `text`
  - 已经适合人阅读的文本
- `status`
  - 该事件发生时 producer 看到的状态
- `created_at`
  - producer 产生事件的时间

说明：

- `text` 必须是“准备给人看”的文本，不是原始 terminal byte stream
- 在 attach mode 下，这个结构更多是 `CodexSessionWatcher` 内部归一化后的事件，而不是外部必须写入的请求体

## 6.2 latest snapshot 模型

daemon 对外提供的 latest output snapshot 建议如下：

```json
{
  "session_id": "active",
  "seq": 42,
  "status": "running",
  "updated_at": "2026-03-14T19:31:08+08:00",
  "latest_text": "当前系统没有现成的 Codex 输出流，所以需要新增 output producer。",
  "recent": [
    {
      "seq": 39,
      "kind": "commentary",
      "text": "我在读取项目结构和相关技能说明。",
      "created_at": "2026-03-14T19:30:14+08:00"
    },
    {
      "seq": 40,
      "kind": "commentary",
      "text": "当前 live 页是 observation 层的一部分，不是独立前端应用。",
      "created_at": "2026-03-14T19:30:38+08:00"
    }
  ],
  "truncated": false
}
```

字段含义：

- `seq`
  - output snapshot 版本号
- `status`
  - `running | idle | no_output`
- `updated_at`
  - 最后一条输出进入 recent window 的时间
- `latest_text`
  - 当前最应该展示的那段文本
- `recent`
  - 最近窗口，按时间顺序排列
- `truncated`
  - 是否因为窗口上限被裁剪

## 6.3 合并后的 live state 模型

为了减少页面请求数，建议新增：

- `GET /live/state.json?token=...&mode=preview|grid`

返回：

```json
{
  "frame": {
    "mode": "preview",
    "updated_at": "2026-03-14T19:31:08+08:00",
    "frame_seq": 120,
    "image_url": "/live/frame.jpg?token=...&mode=preview",
    "desktop_width": 1920,
    "desktop_height": 1080,
    "mouse_position": {
      "x": 840,
      "y": 612
    }
  },
  "output": {
    "seq": 42,
    "status": "running",
    "updated_at": "2026-03-14T19:31:08+08:00",
    "latest_text": "当前系统没有现成的 Codex 输出流，所以需要新增 output producer。",
    "recent": []
  }
}
```

这样 `/live` 页面只需要轮询一个 endpoint。

## 7. API 与 CLI 设计

## 7.1 Public Read API

建议新增：

- `GET /live/output.json?token=...`
- `GET /live/state.json?token=...&mode=preview|grid`

说明：

- `/live/output.json` 用于单独调试 output 区
- `/live/state.json` 给 live 页面主轮询使用
- 两者都复用现有 observation token
- phase1 不要求先暴露独立的“codex output 历史 API”，只返回 bounded latest snapshot 即可

## 7.2 Internal Write API（phase 1 fallback，不是主链路）

建议保留：

- `POST /internal/live-output/events`
- `POST /internal/live-output/status`
- `POST /internal/live-output/reset`

行为：

### `POST /internal/live-output/events`

- 追加一条新输出
- 更新 recent window
- 默认把状态改为 `running`

### `POST /internal/live-output/status`

- 更新状态
- 不一定追加文本
- 用于 turn 完成、空闲、失败等边界时刻

### `POST /internal/live-output/reset`

- 清空 recent window
- 重置 `seq`
- 初始化新 turn 的状态

说明：

- 这一组接口用于测试、兜底、以及未来受控启动模式
- phase 1 的主数据源仍然应是本机 session watcher

## 7.3 CLI 设计

建议在 `src/agent_computer/cli.py` 增加一个新命令组：

```text
agent-computer live-output append --text "..." --kind commentary --status running
agent-computer live-output status --value idle
agent-computer live-output reset
agent-computer live-output show
```

其中：

- `append`
  - 给测试、fallback、受控启动 wrapper 调用
- `status`
  - 显式切换运行状态
- `reset`
  - 新任务开始时清空窗口
- `show`
  - 本机调试当前 latest output snapshot

## 7.4 安全边界

`/internal/live-output/*` 不应走公网反向代理。

部署约束建议明确写入 README / nginx 模板：

1. 只代理 public GET 路由
2. 不代理 `/internal/*`
3. daemon 默认仍绑定 `127.0.0.1`

如果将来必须公网暴露 daemon，再考虑单独 internal token；v1 不建议先做重型安全设计。

## 8. Live 页面 UI 方案

## 8.1 页面结构

页面仍然只有一个 `/live`。

结构调整为两块：

```text
[ Sticky Top Bar ]

[ Screen Live ]

[ Codex Output ]
```

手机优先采用上下布局：

- 上：screen
- 下：output

原因：

1. 符合当前产品描述
2. 屏幕仍然保持主视图
3. output 在手机上更容易按段阅读

## 8.2 布局原则

建议：

- Screen 区域占主空间
- Output 区域固定一个可读高度
- 页面整体单列，不做左右分栏

推荐高度策略：

- Screen 卡片：约 `56vh` 到 `62vh`
- Output 卡片：约 `28vh` 到 `34vh`

如果屏幕较小，优先保证：

- screen 不小于 `220px`
- output 不小于 `180px`

## 8.3 Output 区字段

v1 output 区只显示：

1. 状态 badge
2. 最近更新时间
3. 最新输出文本
4. 最近窗口

不显示：

- 输入框
- 命令按钮
- 复杂 tab
- 多会话列表
- 搜索框

## 8.4 Output 呈现方式

推荐不是用终端黑框模拟器，而是一个适合手机阅读的日志卡片：

- 标题：`Codex Output`
- 状态 badge：`Running / Idle / No Output`
- 最新文本置顶强调
- recent window 用时间顺序轻量堆叠
- 文本自动换行，保留段落

样式约束：

- 继续沿用当前暗色风格，避免突兀
- 字号不低于 `14px`
- 行高 `1.5`
- 触控区域不低于 `44px`
- 最新文本和 recent 之间用轻分隔

## 8.5 自动滚动策略

v1 默认自动 follow 到最新。

实现建议：

- 每次 `output.seq` 变化时，滚动 output 容器到底部
- 因为 recent window 很小，不需要复杂的“暂停自动滚动”开关

## 8.6 页面轮询策略

前端主循环建议改成：

1. 轮询 `/live/state.json`
2. 若 `frame.frame_seq` 变化，刷新图片
3. 若 `output.seq` 变化，重绘 output 区
4. 若只有状态变更，则只改 metadata，不重绘整个列表

实现细节建议：

- 用 `setTimeout` 串行调度下一次 poll
- 不要继续使用固定 `setInterval`

这样可以避免移动网络慢时并发堆积多个 fetch。

## 9. 后端实现落点

## 9.1 新增服务

新增：

- `src/agent_computer/services/live_output_service.py`
- `src/agent_computer/services/codex_session_watcher.py`

建议接口：

- `append_event(...)`
- `set_status(...)`
- `reset(...)`
- `snapshot()`
- `load_from_disk()`
- `persist_snapshot()`

内部实现建议：

- 用 `threading.RLock`
- recent window 用 `collections.deque`
- 每次更新后写 `latest.json.tmp`
- 再原子替换为 `latest.json`

`CodexSessionWatcher` 建议能力：

- `discover_latest_rollout_file()`
- `start()`
- `stop()`
- `poll_once()`
- `parse_line()`
- `switch_rollout_file()`
- `update_heartbeat()`

watcher 配置建议：

- `CODEX_HOME` 默认 `%USERPROFILE%\\.codex`
- session glob：`sessions/*/*/*/rollout-*.jsonl`
- poll 间隔：`500ms` 到 `1000ms`

解析策略建议：

1. 扫描候选文件时，先读取文件开头若干行，找到 `session_meta`
2. 只有 `session_meta.payload.cwd` 与当前项目根匹配，才纳入候选
3. 候选里选择最近修改时间最新的 rollout 文件
4. 进入文件后维护字节 offset，按增量读取
5. 若发现更晚的新匹配 rollout 文件，切换 attach 目标

状态判断建议：

1. 收到 `task_started` 时：`running`
2. 收到 `agent_message` 时：`running` + recent window append
3. 收到 `function_call` / `function_call_output` 时：只刷新 heartbeat
4. 收到 `task_complete` 时：append final + `idle`
5. 没有任何匹配文件时：`no_output`
6. `running` 但 `heartbeat_at` 超过阈值未变化时：前端显示“可能卡住”

## 9.2 SessionService 扩展

修改：

- `src/agent_computer/services/session_service.py`

新增字段建议：

- `_live_output: dict[str, Any] | None`

新增方法：

- `set_live_output(payload)`
- `get_live_output()`

同时扩展 `snapshot()` 输出：

- `live_output_status`
- `live_output_updated_at`
- `live_output_seq`

这样 `/system/health` 也能看到当前 output 状态摘要。

## 9.3 runtime.py 扩展

修改：

- `src/agent_computer/runtime.py`

建议新增：

- `LIVE_OUTPUT_DIR`
- `live_output_latest_path()`

文件建议：

```text
artifacts/
  live-output/
    latest.json
```

这里只存一份 bounded snapshot，不存全量历史。

## 9.4 registry.py 扩展

修改：

- `src/agent_computer/services/registry.py`

新增：

- `live_output: LiveOutputService`
- `codex_session_watcher: CodexSessionWatcher`

让 observation、system、CLI 都能通过 registry 访问同一份 service。

## 9.5 models 扩展

修改：

- `src/agent_computer/models/requests.py`
- `src/agent_computer/models/responses.py`

建议新增：

- `LiveOutputEventRequest`
- `LiveOutputStatusRequest`
- `LiveOutputSnapshotResponse`
- `LiveStateResponse`

这样 API 契约会更稳定，不会把 dict 结构散落到各层。

## 9.6 API 路由

修改：

- `src/agent_computer/api/routes_observation.py`
- 新增 `src/agent_computer/api/routes_live_output.py`
- `src/agent_computer/api/app.py`

具体建议：

### `routes_observation.py`

继续负责：

- `GET /live`
- `GET /live/frame.jpg`
- `GET /live/frame.json`

新增：

- `GET /live/output.json`
- `GET /live/state.json`

### `routes_live_output.py`

负责：

- `POST /internal/live-output/events`
- `POST /internal/live-output/status`
- `POST /internal/live-output/reset`

说明：

- 这个文件在 phase1 可以先建骨架，甚至延后到 phase1.5
- phase1 真正先交付的是 read side，不是 write side

### `app.py`

新增 router 注册。

## 9.7 live 页面 HTML 组织方式

当前 live 页 HTML 直接内嵌在 `routes_observation.py`。

这次增强后，页面复杂度会明显上升。

建议顺手做一个轻量重构：

- 保持无前端构建
- 但把 HTML 生成挪到单独函数或单独模块

建议新增：

- `src/agent_computer/api/live_page.py`

这样路由文件只负责：

- token 校验
- 路由组织
- 调用 `render_live_page(...)`

## 9.8 CLI 接入

修改：

- `src/agent_computer/cli.py`

新增：

- `live-output` 命令组

`windows-launcher.ps1` 当前是透传 CLI 参数，不需要为 `live-output` 额外加白名单逻辑。

## 10. 上游 Codex runtime 集成要求

这不再是 phase 1 的唯一前提。

如果不改上游 runtime / wrapper，phase 1 仍然可以先通过本机 session watcher 闭环。

但如果后续需要“由我们自己启动 Codex 并拿更稳定的实时事件流”，推荐接入点如下：

### 10.1 turn 开始

调用：

- `agent-computer live-output reset`
- `agent-computer live-output status --value running`

### 10.2 commentary 输出

每次有对用户可见的 commentary 文本时：

- `agent-computer live-output append --kind commentary --text "..."`

### 10.3 tool 活动摘要

可选。

如果 runtime 能拿到工具阶段摘要，则附加：

- `agent-computer live-output append --kind tool --text "正在读取 routes_observation.py"`

注意：

- 只发摘要
- 不要把完整 shell 噪音直接灌进 live 页面

### 10.4 final 输出

任务结束时：

- `agent-computer live-output append --kind final --text "..."`
- `agent-computer live-output status --value idle`

### 10.5 error / abort

异常结束时：

- 写入最后一条错误摘要
- 把状态改成 `idle`

这样手机端不会一直停留在“running”。

## 11. 实施步骤

建议按下面顺序做。

### Step 1：Attach Mode 骨架

完成：

- `LiveOutputService`
- `CodexSessionWatcher`
- runtime 路径
- SessionService 扩展
- snapshot 持久化

交付结果：

- daemon 能从本机 `~/.codex/sessions` 产出 latest output 状态

### Step 2：只做高价值事件解析

完成：

- latest rollout file 发现
- tail 新增行
- 事件类型筛选
- 文本抽取与状态映射
- cwd 精确匹配
- 文件切换与 offset 维护

交付结果：

- live 页面已有真实 Codex output 数据源

### Step 3：合并状态读取接口

完成：

- `/live/output.json`
- `/live/state.json`

交付结果：

- 前端只轮询一个状态源即可

### Step 4：live 页面 UI 改造

完成：

- screen + output 双区布局
- mobile-first 样式
- 状态 badge
- recent window 渲染
- “可能卡住”提示

交付结果：

- 手机端可以同时看 screen 和 output

### Step 5：internal ingest API + CLI fallback

完成：

- internal write routes
- `live-output` CLI 命令组

交付结果：

- 测试与未来受控启动模式可把输出写入 daemon

### Step 6：受控启动模式的可选集成

完成：

- commentary mirror
- final mirror
- turn reset / idle status

交付结果：

- 当 future wrapper 接管 Codex 启动时，也能直接吃 `exec --json`

### Step 7：验证与文档

完成：

- README 补充使用方式
- 手动验收 checklist
- nginx / tunnel 文档补充 internal route 边界

## 12. 验收标准

满足以下条件即视为 v1 成功：

1. `/live` 仍是唯一 live 页面入口
2. 默认打开时，上方是屏幕，下方是 Codex Output
3. preview / grid 切换不受影响
4. output 区默认自动更新
5. output 区可显示最近一段文本，而不是空白
6. output 区可显示最近更新时间
7. output 区可显示 `running / idle / no_output`
8. 手机端能同时回答：
   - 现在屏幕在干嘛
   - Codex 刚刚说了什么
   - 它现在是不是还在推进
9. 页面不引入终端输入和远程控制
10. 内部 output 写接口不暴露到公网代理

## 13. 风险与处理

### 风险 1：上游 runtime 没有接 output producer

结果：

- 如果 session watcher 也没接上，live 页面 output 区会停在 `no_output`

处理：

- phase 1 先用本机 session watcher 闭环
- runtime 集成降级为增强项，不再作为第一步硬前提

### 风险 2：输出过于频繁，recent window 被刷屏

处理：

- recent window 做条数和字符数双上限
- tool 只允许摘要，不允许原始日志灌入

### 风险 2.1：session 格式未来变化

处理：

- watcher 只依赖少量稳定字段：
  - `session_meta.payload.cwd`
  - `event_msg.payload.type`
  - `event_msg.payload.message`
  - `event_msg.payload.last_agent_message`
- JSON 解析使用宽松模式，未知字段全部忽略
- `event_msg.agent_message` 不存在时，再回退 `response_item.role=assistant`

### 风险 3：页面轮询增加请求数

处理：

- 用 `/live/state.json` 合并 frame + output
- 图片只有在 `frame_seq` 变化时才刷新

### 风险 4：daemon 重启后 output 丢失

处理：

- 最近窗口 snapshot 持久化到 `artifacts/live-output/latest.json`

### 风险 5：inline HTML 持续膨胀

处理：

- 本次顺手把 live page HTML 提到独立模块

### 风险 6：多仓库 Codex 会话串线

处理：

- 只 attach `session_meta.payload.cwd == 当前项目根` 的 rollout 文件
- 不按“最新文件”全局盲选

### 风险 7：同一仓库多 turn 切换时漏消息

处理：

- watcher 周期性重扫新文件
- 新文件接管时从头读一次
- 之后再进入 offset 增量模式

## 14. 结论

这次增强的关键不是“在 live 页面下方多加一个 div”，而是补齐一条新的 output 数据链路。

技术上最合理的 v1 方案是：

1. 继续复用现有 observation layer 作为 screen 主链路
2. phase1 明确采用 attach mode，不接管 Codex 启动
3. 在 daemon 内新增 `LiveOutputService` 和 `CodexSessionWatcher`
4. 只解析 `task_started / agent_message / task_complete` 等高价值事件
5. phase1 优先读取本机 `~/.codex/sessions/.../rollout-*.jsonl`
6. 在我们接管 Codex 启动时，再补 `codex exec --json` 这条更强的链路
7. 通过 `/live/state.json` 把 screen + output 合并给现有 `/live` 页面
8. 页面保持单页、轮询、手机优先、屏幕优先

这样实现后，`/live` 就会从“只能看动作”升级为“能看动作 + 能看解释 + 能看进度状态”。

## 15. 参考依据

以下依据已在 2026-03-14 核对：

1. 官方 Codex CLI non-interactive 文档明确支持 `codex exec --json`
   - https://developers.openai.com/codex/cli/non-interactive/
2. 社区已经有直接消费 `~/.codex/sessions/.../rollout-*.jsonl` 的实践讨论
   - https://github.com/openai/codex/issues/2288
   - https://github.com/openai/codex/issues/2424
3. 本机 `codex-cli 0.114.0` 已确认存在：
   - `%USERPROFILE%\\.codex\\sessions\\YYYY\\MM\\DD\\rollout-*.jsonl`
   - 且日志中已确认存在 `session_meta / agent_message / task_complete`
