# Agent Computer

一个给 Codex 直接调用的 Windows 桌面原子工具集。

现在它只保留纯桌面控制、Observation latest 与截图强化能力：

- Observation latest preview / grid
- 绝对坐标网格截图
- 轻量预览截图
- 通用截图
- 列出窗口 / 聚焦窗口
- 点击 / 双击 / 移动 / 滚动
- 键盘输入 / 粘贴 / 热键
- 浏览器 URL 直达导航

项目不再内置任何视觉理解模型调用。
如果需要定位元素，推荐流程是：

1. 先确保 daemon 与 Observation Layer 已启动
2. Human 默认看 `/live` 或 latest preview
3. Model 默认取 latest grid image，而不是直接看 `/live` 网页
4. 调用点击、滚动、输入等桌面动作
5. 再读取最新的 latest grid image，确认状态并顺便读取下一步坐标
6. 如此循环

只有在 latest image 看不清楚当前状态、或你需要冻结一张更高确定性的静态图时，才额外使用手动截图做兜底观察。
如果窗口没有最大化，或在截图与点击之间发生了分屏、缩放、尺寸变化，坐标命中率会明显下降。

补充约束：

- 如果目标站点的操作手册已经给出了目标信息，以手册为准
- 当操作没有出现预期行为的时候，首先应该认为是自己的定位不准确

## 1. 创建 conda 环境

```powershell
cd <project-root>
conda env create -p .\.conda -f environment.yml
conda activate .\.conda
pip install -e .
```

## 2. 坐标规则

用于点击联动时，项目遵循这条硬规则：

1. 截图优先使用整屏
2. 坐标原点永远是整张屏幕左上角 `(0,0)`
3. 网格图使用四边标尺带，不把小字压在内容区里
4. 细网格线默认每 `50px` 一条
5. 主网格线每 `100px` 一条，并且只有主网格线会显示坐标标签
6. 红色竖线标签是该主线的 `x`
7. 红色横线标签是该主线的 `y`
8. 未标注的中间 `50px` 细线仍然有效，可用于精确估计点击点
9. 点击阶段直接使用这套整屏绝对坐标，不再做额外换算

## 3. 原子工具

### 3.1 页面进入策略

如果目标是“进入某个已知页面”，优先级应该是：

1. 能拿到可靠 URL：优先直接打开 URL
2. 拿不到 URL，但能构造稳定 URL：优先直接构造并打开
3. 只有在 URL 不可得、需要站内跳转、或必须依赖当前页面状态时，才走 `latest grid image -> 读坐标 -> click -> latest grid image -> ...`

也就是说：

- URL 优先
- 点击兜底

### 3.2 URL 直达导航

如果当前活动窗口已经是浏览器，推荐直接用：

```powershell
agent-computer open-url --url "https://www.zhipin.com/"
agent-computer open-url --url "https://www.zhipin.com/web/geek/jobs?city=101210100&query=agent%E5%BC%80%E5%8F%91" --restore-clipboard
agent-computer browser-back
agent-computer browser-forward
agent-computer browser-refresh
```

这个命令的行为是：

- 发送 `Ctrl+L`
- 把 URL 放进剪贴板并粘贴
- 发送 `Enter`
- `browser-back` 的行为是：`Alt+Left`
- `browser-forward` 的行为是：`Alt+Right`
- `browser-refresh` 的行为是：`Ctrl+R`
- 在操作浏览器网页时，如果误触进入了同一网站的下一个页面，可以直接使用 `browser-back` 返回
- 一般情况下，执行 `browser-back` 之后，可以默认浏览器已经回到上一个页面，并继续使用上一张 frame 推进，而不需要立刻重新查看当前页面
- 例外是会实时变化的网页；这类页面在执行 `browser-back` 之后，仍然建议重新读取 latest image 确认当前状态

### 3.3 Observation latest（默认）

Observation Layer 是默认观察入口，不需要每一步都手动抓图。

- Human 默认入口：`/live?token=<TOKEN>`
- Model 默认入口：`/observation/latest.jpg?token=<TOKEN>&mode=grid`
- Model 默认元数据：`/observation/latest.json?token=<TOKEN>&mode=grid`
- latest preview 仍然保留给 Human 做纯净观察

推荐读取顺序：

1. 启动 daemon
2. 取 `.agent\observation.urls.json`
3. Human 用 `human_live_url`
4. Model 用 `model_default_image_url`
5. 如需确认 freshness，再读 `model_default_meta_url`
6. 如需读取当前鼠标坐标，优先读 `model_mouse_url`

也就是说：

- `/live` 是 Human console
- latest grid image 是 Model default
- `latest.json` 会返回与当前 frame 对齐的 `mouse_position`
- `/observation/mouse.json` 提供当前鼠标的即时坐标
- 手动截图是强化手段，不是默认入口

```powershell
.\windows-launcher.ps1 observation urls
.\windows-launcher.ps1 observation urls --json
agent-computer observation urls --json
agent-computer observation mouse --json
```

### 3.4 网格截图

给 Codex 或人工读取精确坐标用。默认整屏、带绝对坐标网格、高质量 JPEG。
这是手动冻结一张高精度坐标图的方式，不再是默认观察入口。
在执行任何截图前，应先确保目标窗口已经最大化；至少也要保证窗口尺寸在本轮截图到点击之间保持不变。

当前网格的绘制方式是：

- 四边标尺带
- 细网格线每 `50px` 一条
- 主网格线每 `100px` 一条并带标签
- 大号等宽数字只显示在 `100px` 主网格线上
- 标签只画在外围，不遮挡屏幕内容
- 返回坐标仍然是屏幕绝对坐标，不是标尺带的图片像素坐标

```powershell
agent-computer capture-grid
agent-computer capture-grid --grid-size 50 --jpeg-quality 90 --output .\artifacts\grid.jpg
```

推荐使用方式：

1. 默认先看 latest grid image
2. 只有在你需要冻结一张静态高精度坐标图时，再执行 `capture-grid`
3. Codex 查看网格图并读取当前目标坐标
4. `click` / `scroll` / `paste` / `press`
5. 之后回到 latest grid image 持续推进

### 3.5 预览截图

给 Codex 做纯净观察用。默认整屏、无网格、压缩 JPEG。
只有在 latest grid image 看不清当前状态、文字被网格干扰、或你需要单独确认视觉细节时，才建议使用。

```powershell
agent-computer capture-preview
agent-computer capture-preview --output .\artifacts\preview.jpg
```

### 3.6 通用截图

仍然保留通用截图命令，适合调试：

```powershell
agent-computer capture --target primary-screen --format png
agent-computer capture --target active-window --format jpeg --jpeg-quality 70
agent-computer capture --window-title "Windows PowerShell" --grid
```

## 4. 桌面动作命令

列出窗口：

```powershell
agent-computer windows
```

聚焦窗口：

```powershell
agent-computer focus --title "Windows PowerShell"
```

按坐标点击：

```powershell
agent-computer click --x 500 --y 920
agent-computer click --x 500 --y 920 --double
```

滚轮、输入、粘贴、URL 导航、按键、组合键：

```powershell
agent-computer scroll --amount -500
agent-computer type --text "hello world"
agent-computer paste --text "agent开发"
agent-computer paste --text "agent开发" --restore-clipboard
agent-computer open-url --url "https://www.zhipin.com/"
agent-computer browser-back
agent-computer browser-forward
agent-computer browser-refresh
agent-computer press --key enter
agent-computer hotkey ctrl shift s
```

说明：

- `type` 适合 ASCII、快捷测试
- `paste` 更适合中文、长文本、复杂内容
- `open-url` 适合已知目标页面
- `browser-back` / `browser-forward` / `browser-refresh` 适合当前活动浏览器窗口
- `paste` 的行为是：先把指定文本放进 Windows 剪贴板，再发送 `Ctrl+V`
- `open-url` 的行为是：`Ctrl+L -> paste URL -> Enter`

## 5. 推荐给 Codex 的使用方式

默认推荐这样组合，而不是依赖手动截图主导的流程：

1. 如果目标页面 URL 已知，先用 `open-url`
2. 聚焦目标窗口，并确保目标窗口已经最大化
3. 用 `agent-computer observation urls --json` 或 `.agent\observation.urls.json` 拿到默认 observation 入口
4. Model 默认读取 `model_default_image_url`，也就是 latest grid image
5. 如需确认 freshness，再读取 `model_default_meta_url`
6. 如需读取当前鼠标坐标，再读取 `model_mouse_url`
7. 用 `click`、`scroll`、`paste`、`open-url` 等原子动作执行业务步骤
8. 再次读取 latest grid image，并顺便读取下一步坐标
9. 只有当 latest grid image 看不清楚时，才临时使用 `capture-preview`
10. 只有当你需要冻结一张静态高精度网格图时，才使用 `capture-grid`

## 6. 便捷启动

项目根目录自带一个 Windows launcher：

```powershell
.\windows-launcher.ps1 open-url --url "https://www.zhipin.com/"
.\windows-launcher.ps1 browser-back
.\windows-launcher.ps1 browser-forward
.\windows-launcher.ps1 browser-refresh
.\windows-launcher.ps1 observation urls
.\windows-launcher.ps1 capture-grid --grid-size 50
.\windows-launcher.ps1 click --x 500 --y 920
.\windows-launcher.ps1 capture-grid --grid-size 50
.\windows-launcher.ps1 capture-preview
```

现在三层职责明确：

- `agent-computer-daemon` 是核心常驻进程
- `agent-computer` 是正式 CLI 入口
- `.\windows-launcher.ps1` 只负责定位 Windows 本地环境、确保 daemon ready，并把命令转发给正式 CLI

也就是说，`.\windows-launcher.ps1` 不再维护第二套命令定义或参数默认值。

## 7. Observation Layer

项目支持一套统一的 Observation Layer：

- Human 默认入口是 `/live`，并以 `preview` 作为默认展示模式
- Model 默认取 `grid`
- `snapshot` 能力继续保留，不被替代

Observation latest 文件位于：

- `artifacts\observation\preview_latest.jpg`
- `artifacts\observation\grid_latest.jpg`

token 位于：

- `.agent\observation.json`

manifest 位于：

- `.agent\observation.urls.json`

站点手册：

- `BOSS_ZHIPIN_AGENT_MANUAL.md`

核心访问路径：

```text
/live?token=<TOKEN>
/observation/latest.jpg?token=<TOKEN>&mode=preview
/observation/latest.jpg?token=<TOKEN>&mode=grid
/observation/latest.json?token=<TOKEN>&mode=grid
/observation/mouse.json?token=<TOKEN>
```

默认角色分工：

- Human 默认看 `/live`
- Model 默认看 `latest.jpg?mode=grid`
- `latest.json?mode=grid` 用于 freshness / frame meta
- `latest.json?mode=grid` 中的 `mouse_position` 与当前 frame 对齐
- `/observation/mouse.json` 用于读取当前鼠标即时坐标
- `capture-preview` / `capture-grid` 只用于强化观察

推荐拿 URL 的方式：

```powershell
agent-computer observation urls --json
agent-computer observation mouse --json
.\windows-launcher.ps1 observation urls --json
.\scripts\show_observation_urls.ps1
```

推荐启动方式：

```powershell
.\scripts\start_observation_local.ps1
```

如果需要远程访问：

```powershell
.\scripts\start_observation_tunnel.ps1 -RelayHost <public-host> -RelayUser <user>
.\scripts\show_observation_urls.ps1
```

Nginx 反向代理模板位于：

- `deploy\nginx\agent-computer-observation.conf.example`
- `deploy\observation.remote.json.example`
