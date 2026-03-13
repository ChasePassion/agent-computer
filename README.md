# Agent Computer

一个给 Codex 直接调用的 Windows 桌面原子工具集。

现在它只保留纯桌面控制与截图能力：

- 绝对坐标网格截图
- 轻量预览截图
- 通用截图
- 列出窗口 / 聚焦窗口
- 点击 / 双击 / 移动 / 滚动
- 键盘输入 / 粘贴 / 热键
- 浏览器 URL 直达导航

项目不再内置任何视觉理解模型调用。
如果需要定位元素，推荐流程是：

1. 先抓整屏网格图
2. 由 Codex 直接查看网格图并读取当前坐标
3. 调用点击、滚动、输入等桌面动作
4. 再次抓整屏网格图，确认状态并顺便读取下一步坐标
5. 如此循环

只有在网格图看不清楚当前状态时，才额外使用纯净截图做兜底观察。

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
3. 只有在 URL 不可得、需要站内跳转、或必须依赖当前页面状态时，才走 `capture-grid -> 读坐标 -> click -> capture-grid -> ...`

也就是说：

- URL 优先
- 点击兜底

### 3.2 URL 直达导航

如果当前活动窗口已经是浏览器，推荐直接用：

```powershell
agent-computer open-url --url "https://www.zhipin.com/"
agent-computer open-url --url "https://www.zhipin.com/web/geek/jobs?city=101210100&query=agent%E5%BC%80%E5%8F%91" --restore-clipboard
```

这个命令的行为是：

- 发送 `Ctrl+L`
- 把 URL 放进剪贴板并粘贴
- 发送 `Enter`

### 3.3 网格截图

给 Codex 或人工读取精确坐标用。默认整屏、带绝对坐标网格、高质量 JPEG。
这也是默认截图方式。

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

1. `capture-grid`
2. Codex 查看网格图并读取当前目标坐标
3. `click` / `scroll` / `paste` / `press`
4. 再次 `capture-grid` 查看状态并读取下一步坐标
5. 重复这个循环

### 3.4 预览截图

给 Codex 做纯净观察用。默认整屏、无网格、压缩 JPEG。
只有在网格图看不清当前状态、文字被网格干扰、或你需要单独确认视觉细节时，才建议使用。

```powershell
agent-computer capture-preview
agent-computer capture-preview --output .\artifacts\preview.jpg
```

### 3.5 通用截图

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
agent-computer press --key enter
agent-computer hotkey ctrl shift s
```

说明：

- `type` 适合 ASCII、快捷测试
- `paste` 更适合中文、长文本、复杂内容
- `open-url` 适合已知目标页面
- `paste` 的行为是：先把指定文本放进 Windows 剪贴板，再发送 `Ctrl+V`
- `open-url` 的行为是：`Ctrl+L -> paste URL -> Enter`

## 5. 推荐给 Codex 的使用方式

默认推荐这样组合，而不是依赖一个黑盒流程：

1. 如果目标页面 URL 已知，先用 `open-url`
2. 用 `capture-grid` 获取当前整屏网格图
3. 由 Codex 直接查看网格图，读取当前目标坐标
4. 用 `click`、`scroll`、`paste`、`open-url` 等原子动作执行业务步骤
5. 再次 `capture-grid` 查看页面状态，并顺便读取下一步坐标
6. 按 `capture-grid -> 读坐标 -> 动作 -> capture-grid` 的方式循环推进
7. 只有当网格图看不清当前状态时，才临时使用 `capture-preview`

## 6. 便捷启动

项目根目录自带一个包装脚本：

```powershell
.\run.ps1 open-url --url "https://www.zhipin.com/"
.\run.ps1 capture-grid --grid-size 50
.\run.ps1 click --x 500 --y 920
.\run.ps1 capture-grid --grid-size 50
.\run.ps1 capture-preview
```

现在 `.\run.ps1` 会优先直接请求本地 daemon HTTP 接口，而不是每次都重新启动 Python CLI。
这能显著减少 `click`、`focus`、`capture-preview`、`open-url` 这类高频原子动作的单次开销。
`daemon start/status/stop/run` 仍然复用原有 Python 入口。
