# Plan 4: Browser Assist Locator v1

状态：进行中
创建日期：2026-03-14
更新日期：2026-03-14

## 1. 直接结论

你已经明确选择方案 C，所以这份计划不再讨论 “要不要选 WebSocket”，而是直接把方案 C 优化成一个**可落地、可控、不会膨胀成浏览器自动化器**的实现方案。

优化后的推荐结论是：

**采用 Chrome Manifest V3 扩展 + FastAPI WebSocket 桥 + 按需注入 content script + daemon 统一坐标映射 的架构。**

关键收敛点：

1. WebSocket 只负责插件到 daemon 的双向传输，不负责执行动作
2. service worker 只做连接管理和消息路由，不做 DOM 识别
3. content script 只在需要时注入，只在收到 locate 请求时执行
4. daemon 对外仍暴露 HTTP `locate` 接口，WebSocket 只作为插件内部桥
5. 最终执行仍然由 `agent-computer click/type/scroll` 完成

一句话版本：

**WebSocket 做桥，content script 做定位，daemon 做映射，computer 做执行。**

## 2. 当前现状

当前仓库已经具备：

1. 本地 FastAPI daemon
2. `browser-*` 浏览器语义原子命令
3. Observation Layer / latest grid image
4. Windows 屏幕绝对坐标执行链路
5. 前台浏览器窗口校验与当前 URL 读取能力

当前缺失：

1. 浏览器 DOM 级元素定位能力
2. 插件与 daemon 的实时通信通道
3. 几何输出到 screen/grid 坐标的标准映射协议
4. Browser Assist 的完整请求/响应模型

因此，v1 的核心不是“再加一个浏览器命令”，而是新增一个**浏览器辅助定位子系统**。

## 2.1 本次验证结果

基于本轮在 Boss 直聘网页上的只读测试插件验证，已经确认以下事实：

1. 插件通过 `chrome.scripting.executeScript()` 按需注入只读脚本
2. 脚本仅执行 DOM 查询和几何读取，不做点击、输入、滚动
3. 在 `https://www.zhipin.com/web/geek/jobs` 场景下，未出现显性风控反馈：
   - 未跳 `security-check`
   - 未跳 `verify-slider`
   - 未出现页面异常刷新
4. 插件已经能够稳定返回：
   - `page`
   - `viewport`
   - `browser.contentLeftOnScreen`
   - `browser.contentTopOnScreen`
   - `matches[].rect`
   - `matches[].clickablePoint`

这意味着：

- v1 可以把“插件只读定位”作为现实可用前提继续推进
- 当前最优先的问题已经不是“会不会立刻触发风控”
- 而是“如何把现在这个风险验证版探针，演进成正式的通用 locator”

## 3. 官方实现依据

这份优化方案基于两类官方文档约束。

### 3.1 Google Chrome Extensions

根据 Google Chrome Extensions MV3 官方文档：

1. `scripting.executeScript()` 是按需注入脚本的标准方式
2. service worker 与 content script 之间应通过 `runtime.sendMessage()` / `onMessage` 通信
3. Chrome 116 起，**活动中的 WebSocket 连接可以延长 MV3 service worker 生命周期**
4. 官方 keepalive 示例建议每 `20s` 发送一次保活消息

这带来两个直接结论：

1. 方案 C 可以做，但必须建立在 **Chrome 116+** 的前提上
2. 不能把 service worker 当成永不休眠的后台进程，必须显式设计：
   - keepalive
   - reconnect
   - requestId 关联
   - 页面上下文校验

### 3.2 FastAPI

根据 FastAPI 官方文档：

1. WebSocket 端点应显式管理连接接受、收发循环和断连异常
2. 结构化请求仍应走 Pydantic 模型
3. 最合理的形式是：
   - 外部 HTTP API 做业务入口
   - 内部 WebSocket 做实时桥接
   - service 层统一编排

因此本计划明确采用：

- HTTP：
  - 给 agent / 上层调用
- WebSocket：
  - 只给浏览器插件连接

## 4. 方案 C 优化目标

原始方案 C 的问题是：

- WebSocket 很容易把系统做成一个“常驻浏览器代理”
- MV3 生命周期和连接恢复如果设计粗糙，会导致链路很脆
- 多 tab / 多窗口 / 页面切换时，很容易路由错请求

优化后的目标是：

1. 保留 WebSocket 的实时双向优势
2. 避免把插件做成复杂执行器
3. 把连接管理、定位执行、坐标映射三件事拆开
4. 让 v1 只支持**当前前台浏览器 + 当前活动 tab** 的最小闭环

此外，结合本次验证结果，v1 还要额外满足：

5. 插件必须默认采用“只读定位”实现，不引入页面写操作
6. 插件输出必须包含 `browser content anchor`，但映射逻辑仍然保留在后端

## 5. 顶层架构

## 5.1 组件划分

建议新增 5 个组件：

1. Browser Assist Chrome Extension
2. Browser Assist WebSocket Router
3. `BrowserAssistConnectionManager`
4. `BrowserAssistService`
5. Browser Assist API Router

推荐目录结构：

```text
extensions/
└─ browser-assist-locator/
   ├─ manifest.json
   ├─ service_worker.js
   ├─ content_script.js
   ├─ locator.js
   └─ schemas.js

src/agent_computer/
├─ api/
│  ├─ routes_browser_assist.py
│  └─ routes_browser_assist_ws.py
├─ models/
│  └─ browser_assist.py
├─ services/
│  ├─ browser_assist_connection_manager.py
│  └─ browser_assist_service.py
└─ runtime.py

scripts/
├─ package_browser_assist_extension.ps1
└─ test_browser_assist_roundtrip.ps1
```

## 5.2 职责切分

### 扩展 service worker

只负责：

1. 维护 WebSocket 连接
2. 接收 daemon 下发的 locate 请求
3. 选取当前活动 tab
4. 按需注入 content script
5. 将请求转发给 content script
6. 把 content script 结果通过 WebSocket 发回 daemon

不负责：

1. 点击
2. 输入
3. 滚动
4. 多步网页自动化
5. 长链路业务状态机

### content script

只负责：

1. 收集页面状态
2. 执行 DOM 查找
3. 计算 `rect`
4. 计算 `clickablePoint`
5. 返回结构化几何结果

### daemon

负责：

1. 对外提供 HTTP `locate` API
2. 维护插件 WebSocket 会话
3. 把 locate 请求路由到当前浏览器插件
4. 等待结构化结果
5. 做 screen/grid 坐标映射
6. 返回上层 agent

### `agent-computer`

继续只负责：

1. click
2. type
3. scroll
4. screenshot validation

## 6. 为什么方案 C 现在可行

在不优化的情况下，我之前不推荐 C，原因是 MV3 生命周期和连接状态过于脆。

现在之所以可以收敛成可行方案，是因为我们引入了 4 条硬约束：

1. **Chrome 版本下限**
   - v1 明确要求 Chrome / Chromium 116+
   - 依赖“活动 WebSocket 延长 service worker 生命周期”

2. **WebSocket 只是桥**
   - 不把业务逻辑放进 WS 层
   - WS 只传输结构化消息

3. **按需注入**
   - 不做全页面常驻复杂 content script
   - 每次 locate 时用 `scripting.executeScript()` 保证脚本存在

4. **单活路由**
   - v1 只允许“当前前台浏览器 + 当前活动 tab”作为合法目标
   - 不做多 tab 智能分发

这样之后，方案 C 的复杂度就被压在可控范围内了。

## 7. 通信设计

## 7.1 外部 API

daemon 对外仍然走 HTTP。

建议新增：

- `POST /browser-assist/locate`
- `GET /browser-assist/status`

原因：

1. 上层 agent 不需要感知 WebSocket
2. 现有仓库 API 风格是 HTTP-first
3. WebSocket 应该被视为插件内部桥接细节

## 7.2 内部 WebSocket

daemon 新增：

- `GET /ws/browser-assist?token=...`

这里的 token 不是 observation token，而是 Browser Assist 专用连接 token。

建议新增：

- `.agent/browser_assist.json`

例如：

```json
{
  "token": "BALV1TOKEN01",
  "created_at": "2026-03-14T04:00:00+08:00",
  "protocol_version": 1
}
```

## 7.3 消息协议

所有 WebSocket 消息必须统一 envelope。

### daemon -> extension

```json
{
  "type": "locate",
  "requestId": "req-123",
  "payload": {
    "query": {
      "text": "收藏",
      "role": "button",
      "hint": "当前职位详情区域里的收藏按钮",
      "selectorHint": null,
      "index": 0
    },
    "options": {
      "visibleOnly": true,
      "interactiveOnly": true,
      "maxCandidates": 5
    }
  }
}
```

### extension -> daemon

```json
{
  "type": "locate-result",
  "requestId": "req-123",
  "payload": {
    "page": {},
    "viewport": {},
    "browser": {},
    "matches": []
  }
}
```

### keepalive

```json
{
  "type": "keepalive",
  "ts": 1773432000
}
```

### hello / register

```json
{
  "type": "hello",
  "payload": {
    "extensionVersion": "0.1.0",
    "browserName": "chrome",
    "browserVersion": "123.0.0.0"
  }
}
```

## 8. 插件侧实现

## 8.1 Manifest

明确使用：

- `Manifest V3`

权限建议：

- `scripting`
- `tabs`
- `host_permissions`
  - `http://*/*`
  - `https://*/*`

这里仍然不推荐只用 `activeTab`。

原因：

1. 我们需要按需注入当前活动页面
2. 这个过程不能依赖每次用户点击扩展图标授权
3. 方案 C 的定位请求来自 daemon，不是用户手势

## 8.2 service worker 连接策略

service worker 启动时尝试连接：

- `ws://127.0.0.1:37688/ws/browser-assist?token=...`

连接成功后：

1. 发送 `hello`
2. 启动 keepalive
3. 进入消息循环

### keepalive 策略

依据 Chrome 官方示例：

- 每 `20s` 发一次 keepalive

目的：

1. 保持 WebSocket 活跃
2. 尽量防止 service worker 提前休眠
3. 让 daemon 能识别连接是否健康

### reconnect 策略

必须实现指数退避：

- 1s
- 2s
- 5s
- 10s
- 20s 上限

并且加入随机抖动，防止反复抖动重连。

## 8.3 活动 tab 选择策略

收到 locate 请求后，service worker 执行：

1. 查询当前最后聚焦窗口的活动 tab
2. 检查 tab URL 是否为 http/https 页面
3. 检查 content script 是否可通信
4. 若不可通信，则按需注入 content script
5. 向该 tab 发送 locate 请求

这一步明确不做：

- 多候选 tab 排序
- 后台标签页定位
- 多窗口并发定位

v1 只支持：

- 当前前台浏览器窗口
- 当前活动网页 tab

## 8.4 content script 设计

content script 只暴露一个 locator handler：

```text
handleLocate(query, options) -> LocatorPayload
```

### 当前探针实现已验证的最小路径

当前风险测试插件实际上已经验证了一条可行的最小定位路径：

1. 收集一组可交互元素：
   - `button`
   - `a[href]`
   - `input[type='button']`
   - `input[type='submit']`
   - `[role='button']`
2. 过滤可见元素：
   - `rect.width > 0`
   - `rect.height > 0`
   - `display != none`
   - `visibility != hidden`
   - `pointer-events != none`
   - 元素位于当前 viewport 内
3. 读取元素文本：
   - `innerText`
   - `textContent`
   - `value`
4. 基于文本命中目标元素
5. 使用 `getBoundingClientRect()` 生成：
   - `rect`
   - `clickablePoint`

这条路径已经被 Boss 页面上的“立即沟通”验证过，因此它可以作为正式 locator 的起点，而不是重新发明另一套识别逻辑。

### DOM 查找规则

推荐分层筛选：

1. 先收集候选：
   - `button`
   - `a[href]`
   - `input`
   - `textarea`
   - `[role]`
2. 按 `role` 过滤
3. 按 `visibleOnly` 过滤
4. 按 `interactiveOnly` 过滤
5. 按 `text` 命中过滤
6. 按 `hint` 做规则增强
7. 截断到 `maxCandidates`

正式版的演进方式应该是：

- 保留当前探针这条“可交互元素筛选 + 可见性过滤 + 文本匹配 + `getBoundingClientRect()`”主链
- 把硬编码文本替换成 `query + options`
- 把单结果输出替换成 `matches[]`
- 把当前返回的 `page/viewport/browser` 固化为正式协议

### hint 处理原则

v1 不在插件里做自由语义推理。

只做规则增强：

1. 祖先容器文本命中
2. 常见区域关键词命中
   - 顶部
   - 右侧
   - 弹窗
   - 当前详情区域
3. `selectorHint` 只作为增强项，不作为主路径

## 9. daemon 侧实现

## 9.1 API 设计

### `POST /browser-assist/locate`

用途：

- 给上层 agent 一个同步的 HTTP 入口

流程：

1. 校验前台窗口是浏览器
2. 校验 Browser Assist WebSocket 已连接
3. 生成 `requestId`
4. 通过 WebSocket 下发 locate 消息
5. 等待同 `requestId` 的结果
6. 做映射
7. 返回响应

建议默认超时：

- `3s`

### `GET /browser-assist/status`

返回：

1. WebSocket 是否已连接
2. 最后一次心跳时间
3. 最近一次活动浏览器信息
4. 当前支持协议版本

## 9.2 Service 结构

建议新增：

- `BrowserAssistConnectionManager`
- `BrowserAssistService`

### `BrowserAssistConnectionManager`

职责：

1. 接收 WebSocket 连接
2. 保存当前活动扩展连接
3. 维护 `requestId -> Future`
4. 派发 locate 请求
5. 接收 locate-result 并唤醒等待方
6. 处理断连、超时、异常清理

### `BrowserAssistService`

职责：

1. 校验浏览器上下文
2. 调用连接管理器下发请求
3. 校验插件返回结构
4. 做 screen/grid 映射
5. 返回 HTTP 响应

## 9.3 FastAPI WebSocket 设计

建议新增：

- `routes_browser_assist_ws.py`

形式：

```text
GET /ws/browser-assist?token=...
```

连接阶段要做：

1. token 校验
2. `accept()`
3. 进入消息接收循环
4. 捕获 `WebSocketDisconnect`
5. 释放连接状态

这部分严格按 FastAPI / Starlette 的 WebSocket 方式实现，不把业务逻辑塞进路由函数。

## 10. 坐标映射方案

方案 C 优化后，IPC 变了，但坐标映射原则不变。

## 10.1 坐标系统

v1 必须明确 3 套坐标：

1. DOM / viewport 坐标
   - `getBoundingClientRect()`
   - 单位：CSS pixel
2. 浏览器内容区锚点
   - 插件采集
   - 单位：CSS pixel
3. `agent-computer` screen/grid 坐标
   - 单位：物理屏幕像素

本次插件验证已经说明：

- `clickablePoint` 和 `rect` 取自 DOM / viewport 的 CSS pixel 空间
- `browser.contentLeftOnScreen / contentTopOnScreen` 可以由插件侧返回
- 但**screen 映射必须仍由 daemon 完成**

也就是说：

- 插件负责采集锚点
- daemon 负责映射
- 不允许把桌面点击坐标的最终计算下放到插件

## 10.2 推荐映射公式

```text
css_abs_x = browser.contentLeftOnScreen + viewport.offsetLeft + clickablePoint.x
css_abs_y = browser.contentTopOnScreen + viewport.offsetTop + clickablePoint.y

screen_x = round(css_abs_x * page.devicePixelRatio)
screen_y = round(css_abs_y * page.devicePixelRatio)
```

## 10.3 二次校验

映射前必须做：

1. 当前前台窗口仍是浏览器
2. 插件回传 `page.url` 与 daemon 当前 `browser-current-url` 一致或高度接近
3. 扩展回传 title 与前台窗口 title 高度接近

如果不一致：

- 直接报错
- 不允许继续点击

这样可以避免：

- service worker 连着的是浏览器
- 但实际前台窗口已经切走
- 结果却仍被错误执行

## 10.4 browser content anchor 的实现要求

结合本次测试插件，`browser content anchor` 已经证明可以返回，因此正式版应把它升格为协议中的必要字段。

正式版至少要返回：

```json
"browser": {
  "contentLeftOnScreen": 0,
  "contentTopOnScreen": 121,
  "raw": {
    "screenX": 0,
    "screenY": 0,
    "outerWidth": 1536,
    "outerHeight": 816,
    "innerWidth": 1536,
    "innerHeight": 695
  }
}
```

这里要明确两层语义：

1. `contentLeftOnScreen` / `contentTopOnScreen`
   - 是插件对浏览器内容区原点的估计值
   - 直接参与后端映射
2. `raw`
   - 是供 daemon 校验和后续修正用的原始几何信息
   - 不直接视为最终可点击坐标

正式版要求：

- `browser content anchor` 必须返回
- `raw browser geometry` 建议一并返回
- 映射逻辑禁止在插件里执行

## 11. Phase 划分

## Phase 1：协议、WS 骨架、HTTP 外部入口

边界：

- 只完成后端协议和连接管理基础设施

交付：

1. `browser_assist.py` 模型
2. `BrowserAssistConnectionManager`
3. `BrowserAssistService` 骨架
4. `POST /browser-assist/locate`
5. `GET /browser-assist/status`
6. `GET /ws/browser-assist`

不在本 phase 内：

- content script 定位逻辑
- Boss 页面验收

## Phase 2：扩展最小闭环

边界：

- 打通 service worker -> content script -> daemon 的 locate 回路

交付：

1. manifest
2. service worker WebSocket 客户端
3. keepalive + reconnect
4. 按需注入 content script
5. 基于当前探针的最小 DOM locate 能力
6. `browser content anchor` 返回

不在本 phase 内：

- 高级 hint 规则
- 多浏览器支持

## Phase 3：映射、校验、降级

边界：

- 把定位结果稳定变成 screen/grid 绝对坐标

交付：

1. CSS pixel -> physical pixel 映射
2. URL / title / foreground browser 二次校验
3. 结构化错误模型
4. 回退 pure-grid 的降级策略
5. 基于 `raw browser geometry` 的 anchor 校正策略

## Phase 4：真实业务页验收

边界：

- 只做高价值真实网页验证

交付：

1. Boss 收藏按钮
2. Boss 立即沟通按钮
3. 顶部搜索框
4. 文档与调试指南

## 12. 关键决策点

## 12.1 权限模型

选项：

1. `activeTab`
2. `host_permissions + scripting`

推荐：

- `host_permissions + scripting`

理由：

- 方案 C 的 locate 请求来自 daemon，不是用户手势
- 要支持按需注入，不能把授权建立在扩展图标点击上

## 12.2 WebSocket 生命周期

选项：

1. 连接断了完全依赖浏览器重建
2. 显式 keepalive + reconnect

推荐：

- 显式 keepalive + reconnect

理由：

- 这是方案 C 能否稳定的生命线

## 12.3 content script 注入方式

选项：

1. 所有页面常驻 content script
2. 按需注入

推荐：

- 按需注入

理由：

1. 更符合 locator-only
2. 更小权限、更小资源占用
3. 便于把问题限定在“当前请求对应的当前页面”

## 13. 错误与降级策略

必须定义至少 6 类错误：

1. 前台不是浏览器
2. Browser Assist WebSocket 未连接
3. 当前 tab 非 http/https 页面
4. content script 注入失败
5. 查询无匹配项
6. 页面上下文与 daemon 当前状态不一致

统一返回结构建议：

```json
{
  "error": {
    "type": "browser_assist_extension_offline",
    "message": "Browser Assist extension is not connected.",
    "details": {}
  }
}
```

降级顺序：

1. Browser Assist 失败
2. 返回结构化错误
3. 上层 agent 决定是否退回 grid 目测定位

明确不做：

- 扩展失败时自动帮用户盲点

## 14. 文件落点建议

### Python 侧

- `src/agent_computer/models/browser_assist.py`
- `src/agent_computer/services/browser_assist_connection_manager.py`
- `src/agent_computer/services/browser_assist_service.py`
- `src/agent_computer/api/routes_browser_assist.py`
- `src/agent_computer/api/routes_browser_assist_ws.py`

### 扩展侧

- `extensions/browser-assist-locator/manifest.json`
- `extensions/browser-assist-locator/service_worker.js`
- `extensions/browser-assist-locator/content_script.js`
- `extensions/browser-assist-locator/locator.js`
- `extensions/browser-assist-locator/schemas.js`

### 脚本

- `scripts/package_browser_assist_extension.ps1`
- `scripts/test_browser_assist_roundtrip.ps1`

## 15. 验证方式

## 15.1 单元验证

至少验证：

1. Pydantic 请求模型
2. WebSocket 消息 envelope 校验
3. requestId 匹配与超时处理
4. 坐标映射函数
5. URL / title / foreground browser 校验

## 15.2 集成验证

至少验证：

1. 扩展连接 daemon 成功
2. keepalive 正常更新
3. daemon 发 locate，扩展能回结构化结果
4. 断开浏览器后可自动重连

## 15.3 真实场景验收

以 Boss 为主：

1. 收藏
2. 立即沟通
3. 搜索框
4. 只读探针执行后页面无显性风控反馈

成功标准：

1. `matches` 非空
2. screen 点落在目标元素区域内
3. 点击后页面反馈正确
4. 只读定位不触发 `security-check` / `verify-slider`

## 16. 风险

## 风险 1：service worker 仍然意外休眠

处理：

1. 依赖 Chrome 116+
2. 保持活动 WebSocket
3. 每 20s keepalive
4. reconnect + status 可观测

## 风险 2：前台浏览器与活动 tab 不一致

处理：

1. locate 前校验 foreground browser
2. 校验当前 URL / title
3. 不一致直接 fail fast

## 风险 3：WebSocket 成了状态机泥潭

处理：

1. WebSocket 只负责 transport
2. 外部业务入口仍走 HTTP
3. 只支持单活动 session
4. 所有请求必须带 `requestId`

## 风险 4：插件边界膨胀

处理：

- 扩展侧永远不实现 click/type/scroll

## 风险 5：browser content anchor 估值不准

处理：

1. 插件返回 `raw browser geometry`
2. daemon 用当前前台窗口 rect 二次修正
3. 映射后继续用 Observation 做闭环验证

## 17. 最终建议

既然你已经选了方案 C，最重要的不是再去争论 “C 是否最好”，而是把 C 收敛成下面这个形态：

1. WebSocket 只做 transport
2. service worker 只做连接和路由
3. content script 只做定位
4. daemon 只对外暴露 HTTP locate
5. 坐标映射和执行继续留在 `agent-computer`
6. 正式 locator 直接从本次已验证的只读 DOM 探针演进，不另起一套识别路线

如果按这个优化版推进，方案 C 是可以落地的，而且不会偏成浏览器自动化器。

真正需要盯死的不是“WebSocket 能不能连上”，而是：

**定位结果能不能在前台浏览器真实上下文下，稳定映射成 screen/grid 绝对坐标。**
