# Plan 1: Agent Computer Daemon Service Refactor

## 1. 背景

当前 `agent-computer` 已具备一组可用的原子能力：

- `capture-preview`
- `capture-grid`
- `locate`
- `focus`
- `click`
- `paste`
- `open-url`
- `scroll`
- `press`
- `hotkey`

但当前实现仍然以单次 CLI 调用为中心，主要问题是：

1. 每个命令都会重新启动 Python 进程
2. CLI handler 同时承担参数解析、业务编排、执行逻辑
3. 动作层、截图层、Gemini 层没有稳定服务边界
4. 后续如果直接接 MCP，会把当前尚未稳定的工具接口过早固化
5. 产品化安装和集成方式还不适合“一行配置即可使用”

因此，Phase 1 的目标不是直接做 MCP，而是先把 `agent-computer` 重构成一个稳定的本地常驻核心。

## 2. Phase 1 目标

Phase 1 只解决一件事：

**把当前 CLI 驱动的工具集，重构为“服务层 + 常驻 daemon + 薄 CLI”结构。**

预期收益：

- 显著降低单次命令启动耗时
- 统一内部调用入口，便于后续接 MCP
- 让工具接口更稳定、更适合产品化分发
- 为后续一行安装、自启动、AI 客户端接入打基础

## 3. Phase 1 非目标

以下内容不属于本阶段主目标：

1. 不先做 MCP 主接入层
2. 不做 Windows Service 形态
3. 不做 Named Pipe 极致性能优化
4. 不在本阶段大改视觉策略或引入 UIA 大重构
5. 不在本阶段实现完整 GUI 或托盘产品界面

说明：

- MCP 是 Phase 2 接入层
- Windows Service 不适合当前桌面交互场景
- 先把本地 daemon 打磨稳定，比先暴露 MCP 更重要

## 4. 目标架构

### 4.1 架构原则

核心原则：

1. 内核能力只实现一份
2. CLI 只做调用，不再直接执行业务
3. daemon 是唯一常驻执行核心
4. HTTP API 是内部稳定接口
5. MCP 未来只做适配层，不直接承载核心逻辑

### 4.2 目标结构

```text
agent-computer
├─ src/agent_computer/
│  ├─ services/
│  │  ├─ capture_service.py
│  │  ├─ action_service.py
│  │  ├─ navigation_service.py
│  │  ├─ gemini_service.py
│  │  └─ session_service.py
│  ├─ api/
│  │  ├─ app.py
│  │  ├─ routes_capture.py
│  │  ├─ routes_actions.py
│  │  ├─ routes_navigation.py
│  │  └─ routes_gemini.py
│  ├─ models/
│  │  ├─ requests.py
│  │  └─ responses.py
│  ├─ cli.py
│  ├─ daemon.py
│  └─ ...
├─ run.ps1
└─ docs/dev/phase1/...
```

### 4.3 运行形态

目标运行形态：

1. `agent-computer daemon`
   启动本地常驻服务
2. `agent-computer <subcommand>`
   CLI 仅作为 daemon client
3. daemon 监听 `127.0.0.1:<port>`
4. 重型对象在 daemon 启动时只初始化一次

## 5. 服务拆分方案

### 5.1 Capture Service

职责：

- 统一管理截图能力
- 支持 preview/grid/common capture
- 统一 sidecar 元数据生成
- 统一图片格式和质量策略

接口示例：

- `capture_preview()`
- `capture_grid(grid_size, jpeg_quality)`
- `capture(target, options)`

### 5.2 Action Service

职责：

- 统一管理桌面动作
- 负责鼠标、键盘、滚轮、剪贴板粘贴

接口示例：

- `click(x, y, button, double)`
- `move(x, y, duration)`
- `scroll(amount)`
- `type_text(text, interval)`
- `paste(text, restore_clipboard)`
- `press(key)`
- `hotkey(keys)`

### 5.3 Navigation Service

职责：

- 聚焦窗口
- 浏览器地址栏导航
- URL 优先策略统一收口

接口示例：

- `list_windows()`
- `focus_window(title, exact)`
- `open_url(url, restore_clipboard)`

### 5.4 Gemini Service

职责：

- 统一管理 Gemini client 生命周期
- 统一提示词拼接规则
- 统一重试、超时、JSON 结构化返回

接口示例：

- `analyze_image(image_path, prompt)`
- `locate(image_path, target_description)`

### 5.5 Session Service

职责：

- daemon 级共享状态
- 最近截图、最近窗口、最近请求结果缓存
- 后续可扩展为 wait / cache / trace

接口示例：

- `health()`
- `get_last_capture()`
- `set_last_capture(meta)`
- `set_last_locate(result)`

## 6. API 设计

Phase 1 API 只保留最小集合。

### 6.1 基础接口

- `GET /health`
- `GET /version`

### 6.2 截图接口

- `POST /capture/preview`
- `POST /capture/grid`
- `POST /capture`

### 6.3 动作接口

- `POST /actions/click`
- `POST /actions/move`
- `POST /actions/scroll`
- `POST /actions/type`
- `POST /actions/paste`
- `POST /actions/press`
- `POST /actions/hotkey`

### 6.4 导航接口

- `GET /windows`
- `POST /focus`
- `POST /open-url`

### 6.5 Gemini 接口

- `POST /ocr`
- `POST /locate`

### 6.6 API 要求

所有接口统一要求：

1. JSON request / JSON response
2. 错误结构统一
3. 返回字段稳定，不混用纯文本和 JSON
4. 所有路径字段用绝对路径
5. 响应中保留调试字段，但使用统一命名

## 7. CLI 重构方案

### 7.1 当前问题

当前 `cli.py` 同时承担：

- 参数解析
- 业务执行
- 文件输出
- 调试打印

这导致 CLI 很重，也不适合复用。

### 7.2 重构目标

CLI 只做三件事：

1. 解析命令行参数
2. 检查 daemon 是否可用
3. 调用本地 API 并输出结果

### 7.3 CLI 行为目标

目标行为：

- daemon 已运行：直接调用
- daemon 未运行：可选自动启动并等待 ready
- `run.ps1` 只调用新 CLI，不再承载逻辑

## 8. 实施步骤

### Step 1: 抽服务层

从当前代码中抽出：

- `capture_service`
- `action_service`
- `navigation_service`
- `gemini_service`

完成标准：

- CLI handler 不再直接依赖底层模块函数
- 所有核心能力都可由 service API 调用

### Step 2: 定义请求/响应模型

新增：

- `models/requests.py`
- `models/responses.py`

完成标准：

- 所有 API 和 CLI 调用共用同一套数据模型
- 错误格式统一

### Step 3: 实现 daemon

新增：

- `daemon.py`
- `api/app.py`
- 路由模块

完成标准：

- daemon 启动后一次性初始化重型对象
- 本地 HTTP API 可用
- 至少支持最小 API 集合

### Step 4: 改造 CLI 为薄客户端

完成标准：

- CLI 不再直接调用 service 内核
- CLI 默认走 daemon
- 结果输出保持兼容 JSON 风格

### Step 5: 增加 daemon 管理命令

建议新增：

- `agent-computer daemon start`
- `agent-computer daemon stop`
- `agent-computer daemon status`

完成标准：

- 本地开发和产品调试更容易
- 为后续安装脚本做准备

### Step 6: 验证关键链路

至少验证：

1. `focus -> open-url -> capture-preview`
2. `capture-grid -> locate -> click`
3. `paste` 中文输入
4. Gemini 超时/重试逻辑

## 9. 验收标准

Phase 1 完成后，必须满足：

1. `agent-computer` CLI 默认通过 daemon 工作
2. 单次原子命令调用延迟明显低于当前多进程模式
3. URL 导航链路稳定
4. Gemini 调用链路仍可用
5. JSON 返回结构稳定
6. 代码内核已和 CLI 解耦
7. 后续可无缝加 MCP adapter

## 10. 风险与处理

### 风险 1: 桌面交互上下文丢失

处理：

- daemon 必须运行在当前用户登录会话内
- 不做 Windows Service

### 风险 2: CLI 与 daemon 返回结构不一致

处理：

- 所有 response 使用统一模型
- CLI 只做转发和轻量格式化

### 风险 3: 过早固化不成熟接口

处理：

- Phase 1 不先暴露 MCP
- 先稳定 HTTP API

### 风险 4: 调试难度上升

处理：

- 增加 `health`, `version`, `status`
- 明确日志与错误输出规范

## 11. Phase 1 交付物

本阶段交付物应包括：

1. 常驻 daemon
2. 薄 CLI
3. 服务层拆分后的代码结构
4. 统一请求/响应模型
5. 基础健康检查接口
6. 更新后的开发文档

## 12. 后续阶段建议

### Phase 2

- MCP adapter
- 更强等待机制
- 状态缓存
- URL / 页面状态工具补强

### Phase 3

- 一键安装脚本
- 登录自启动
- 托盘/状态管理
- 产品化配置界面

## 13. 结论

Phase 1 应专注于：

**先把 `agent-computer` 做成一个稳定、常驻、可复用的本地执行核心。**

顺序必须是：

1. 服务层拆分
2. daemon
3. 薄 CLI
4. 再做 MCP

这条路径最稳，也最适合后续产品化和“一行安装”的目标。
