# Plan 2: Browser Navigation Commands

状态：已完成
完成日期：2026-03-13

## 1. 背景

当前 `agent-computer` 已经具备一组通用桌面原子能力：

- `focus`
- `open-url`
- `move`
- `click`
- `scroll`
- `press`
- `hotkey`

但在浏览器场景里，仍然缺少 3 个高频且语义明确的原子操作：

1. 返回上一页
2. 前进到下一页
3. 刷新当前页面

当前如果想完成这些动作，只能由上层代理自行拼装：

- `hotkey alt left`
- `hotkey alt right`
- `hotkey ctrl r`

这存在几个问题：

1. 语义不清晰，上层需要知道浏览器快捷键
2. 不利于 agent 规划，把“导航意图”降级成了“按键细节”
3. 容易在非浏览器窗口误触
4. 无法统一增加浏览器前台校验与稳定错误返回

因此需要新增一组**浏览器语义化导航原子命令**。

## 2. 命令命名

本计划确认命名采用 `browser-` 前缀，而不是裸命令。

最终 CLI 命令名：

- `browser-back`
- `browser-forward`
- `browser-refresh`

对应含义：

- `browser-back`：浏览器返回上一页
- `browser-forward`：浏览器前进到下一页
- `browser-refresh`：浏览器刷新当前页

采用前缀的原因：

1. 与通用键盘动作 `press` / `hotkey` 明确区分
2. 防止未来与其他导航语义命令重名
3. 对 agent 更直接，看到命令名就能理解“仅用于浏览器”

## 3. Phase 2 目标

本阶段只解决一件事：

**把浏览器前进 / 后退 / 刷新，从“上层拼热键”提升为“项目内建语义原子命令”。**

预期收益：

- 降低上层代理的规划复杂度
- 提升浏览器自动化场景稳定性
- 为后续继续补充浏览器语义原子操作建立模式

## 4. 非目标

以下内容不在本计划范围：

1. 不引入 Playwright、Selenium、CDP
2. 不做浏览器 DOM 识别
3. 不自动识别浏览器品牌并做差异化快捷键策略
4. 不实现标签页管理命令
5. 不实现浏览器历史记录读取能力

说明：

- 这一阶段只做“当前活动浏览器窗口”的 3 个基础导航命令

## 5. 设计原则

### 5.1 语义高于按键

对上层暴露：

- `browser-back`
- `browser-forward`
- `browser-refresh`

而不是暴露：

- `alt+left`
- `alt+right`
- `ctrl+r`

### 5.2 统一放在 Navigation 层

这 3 个命令虽然底层仍然通过快捷键执行，但它们表达的是“页面导航意图”，因此应放在 `navigation` 层，而不是 `actions` 层。

原因：

1. 当前 `open-url` 已经属于导航语义
2. 返回 / 前进 / 刷新与 URL 导航同属浏览器页面控制
3. 便于未来扩展更多浏览器语义命令

## 6. 目标接口

### 6.1 HTTP API

新增接口：

- `POST /navigation/browser-back`
- `POST /navigation/browser-forward`
- `POST /navigation/browser-refresh`

请求体：

- 无请求体

响应示例：

```json
{
  "operation": "browser-back",
  "keys": ["alt", "left"]
}
```

```json
{
  "operation": "browser-forward",
  "keys": ["alt", "right"]
}
```

```json
{
  "operation": "browser-refresh",
  "keys": ["ctrl", "r"]
}
```

### 6.2 CLI

新增 CLI 子命令：

- `agent-computer browser-back`
- `agent-computer browser-forward`
- `agent-computer browser-refresh`

### 6.3 PowerShell 包装脚本

新增根目录脚本调用形式：

- `.\windows-launcher.ps1 browser-back`
- `.\windows-launcher.ps1 browser-forward`
- `.\windows-launcher.ps1 browser-refresh`

## 7. 代码落点

### 7.1 底层动作封装

文件：

- `src/agent_computer/actions.py`

新增函数：

- `browser_back()`
- `browser_forward()`
- `browser_refresh()`

建议实现：

```python
def browser_back() -> None:
    pyautogui.hotkey("alt", "left")

def browser_forward() -> None:
    pyautogui.hotkey("alt", "right")

def browser_refresh() -> None:
    pyautogui.hotkey("ctrl", "r")
```

### 7.2 Navigation Service

文件：

- `src/agent_computer/services/navigation_service.py`

新增方法：

- `browser_back()`
- `browser_forward()`
- `browser_refresh()`

职责：

1. 调用底层动作函数
2. 返回统一结构化 JSON

### 7.3 Navigation API

文件：

- `src/agent_computer/api/routes_navigation.py`

新增路由：

- `@router.post("/browser-back")`
- `@router.post("/browser-forward")`
- `@router.post("/browser-refresh")`

### 7.4 请求模型

文件：

- `src/agent_computer/models/requests.py`

v1 不新增请求模型。

原因：

- 这 3 个接口无请求体
- 可以直接定义为无参路由

### 7.5 CLI

文件：

- `src/agent_computer/cli.py`

需要修改两处：

1. `_handle_remote()` 增加三个分支
2. `build_parser()` 增加三个子命令

### 7.6 PowerShell Wrapper

文件：

- `windows-launcher.ps1`

launcher 只需要保证这些命令可以原样透传：

- `browser-back`
- `browser-forward`
- `browser-refresh`

这三个命令：

1. 不接受额外参数
2. 直接发到对应 `/navigation/...` 路由

### 7.7 README

文件：

- `README.md`

需要补充：

1. 新命令说明
2. 使用示例
3. “当前浏览器前台窗口”这一约束

## 8. 实施步骤

### Step 1: 底层动作补齐

在 `actions.py` 中新增：

- `browser_back`
- `browser_forward`
- `browser_refresh`

### Step 2: 导航服务接入

在 `NavigationService` 中增加三项浏览器导航方法。

### Step 3: API 暴露

在 `routes_navigation.py` 中新增 3 个 POST 路由。

### Step 4: CLI 暴露

在 `cli.py` 中新增：

- `browser-back`
- `browser-forward`
- `browser-refresh`

### Step 5: `windows-launcher.ps1` 透传

在 `windows-launcher.ps1` 中不新增第二套命令实现，只负责透传到正式 CLI。

### Step 6: 文档更新

更新 `README.md`，并补充使用示例。

### Step 7: 冒烟测试

手工验证以下场景：

1. Chrome 前台执行 `.\windows-launcher.ps1 browser-back`
2. Chrome 前台执行 `.\windows-launcher.ps1 browser-forward`
3. Chrome 前台执行 `.\windows-launcher.ps1 browser-refresh`

## 9. 验收标准

满足以下条件即视为完成：

1. 三个命令在 CLI、daemon API 可用，`windows-launcher.ps1` 可无额外解析地透传调用
2. 返回结构化 JSON
3. README 中有明确示例

## 10. 风险与处理

### 风险 1：当前浏览器未聚焦

处理：

- 文档中明确要求先执行 `focus`
- 不在 v1 强制自动帮用户聚焦浏览器

### 风险 2：快捷键在个别浏览器不一致

处理：

- v1 仅支持常见桌面浏览器默认快捷键
- 若后续发现差异，再在服务层做浏览器分支

## 11. 推荐文档示例

README 建议增加的示例：

```powershell
.\windows-launcher.ps1 focus --title "Google Chrome"
.\windows-launcher.ps1 browser-back
.\windows-launcher.ps1 browser-forward
.\windows-launcher.ps1 browser-refresh
```

## 12. 结论

本计划的核心不是新增 3 个热键，而是新增 3 个**浏览器语义原子能力**。

最终对上层代理暴露的是：

- `browser-back`
- `browser-forward`
- `browser-refresh`

而不是底层快捷键细节。

这会让 `agent-computer` 在浏览器控制场景中明显更好用，也为后续继续增加浏览器语义原子命令打下统一模式。
