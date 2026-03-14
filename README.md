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
- 在点击之后没有出现预期结果时，先获取当前鼠标坐标信息，再对照最新网格图片复核，优先排查是否因为坐标偏差导致点击没有落在目标上
- 每次对目标开始操作之前，首先阅读相关的 skill / 操作手册
- 思考一切可行办法去完成用户的需求；在用户需求被完成之前，不要因为单次失败、页面异常或路径不顺手就停止
- 当实际操作时出现“操作手册中不存在的行为 -> 结果映射”时，需要把新映射追加到对应手册中
- 追加手册时，至少记录当时的 URL、鼠标坐标、触发动作和页面反馈

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
agent-computer browser-open-url --url "https://www.zhipin.com/"
agent-computer browser-open-url --url "https://www.zhipin.com/web/geek/jobs?city=101210100&query=agent%E5%BC%80%E5%8F%91" --restore-clipboard
agent-computer browser-current-url
agent-computer browser-back
agent-computer browser-forward
agent-computer browser-refresh
```

这个命令的行为是：

- 发送 `Ctrl+L`
- 把 URL 放进剪贴板并粘贴
- 发送 `Enter`
- `browser-current-url` 的行为是：校验前台窗口是浏览器，再执行 `Ctrl+L -> Ctrl+C -> Esc` 读取当前地址栏 URL
- `browser-back` 的行为是：`Alt+Left`
- `browser-forward` 的行为是：`Alt+Right`
- `browser-refresh` 的行为是：`Ctrl+R`
- 在操作浏览器网页时，如果误触进入了同一网站的下一个页面，可以直接使用 `browser-back` 返回
- 一般情况下，执行 `browser-back` 之后，可以默认浏览器已经回到上一个页面，并继续使用上一张 frame 推进，而不需要立刻重新查看当前页面
- 例外是会实时变化的网页；这类页面在执行 `browser-back` 之后，仍然建议重新读取 latest image 确认当前状态

### 3.3 Observation latest（默认）

Observation Layer 是默认观察入口，不需要每一步都手动抓图。

- Human 默认入口：`/live?token=<TOKEN>`
- Human live frame 接口：`/live/frame.jpg?token=<TOKEN>&mode=preview|grid`
- Human live meta 接口：`/live/frame.json?token=<TOKEN>&mode=preview|grid`
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
- `/live/frame.*` 仅给 Human live 页面使用，可在 preview / grid 之间切换
- latest grid image 是 Model default
- `latest.json` 会返回与当前 frame 对齐的 `mouse_position`
- `/observation/mouse.json` 提供当前鼠标的即时坐标
- `/observation/latest.*` 现在只支持 `mode=grid`，用于 AI / model 侧
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
agent-computer maximize --title "Google Chrome"
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
agent-computer browser-open-url --url "https://www.zhipin.com/"
agent-computer browser-back
agent-computer browser-forward
agent-computer browser-refresh
agent-computer press --key enter
agent-computer hotkey ctrl shift s
```

说明：

- `type` 适合 ASCII、快捷测试
- `paste` 更适合中文、长文本、复杂内容
- `browser-open-url` 适合已知目标页面
- `browser-current-url` 适合确认当前浏览器真实落点
- `browser-back` / `browser-forward` / `browser-refresh` 适合当前活动浏览器窗口
- `paste` 的行为是：先把指定文本放进 Windows 剪贴板，再发送 `Ctrl+V`
- `browser-open-url` 的行为是：`Ctrl+L -> Ctrl+A -> paste URL -> Enter`

## 5. 推荐给 Codex 的使用方式

默认推荐这样组合，而不是依赖手动截图主导的流程。

### 5.1 通用桌面链路

适用场景：

- 桌面原生应用
- 没有 Browser Assist 的网页
- 需要直接按屏幕坐标推进的场景

1. 如果目标页面 URL 已知，先用 `browser-open-url`
2. 聚焦目标窗口，并确保目标窗口已经最大化
   推荐顺序：先 `focus`，再 `maximize`
3. 开始操作之前，先阅读相关的 skill / 操作手册
4. 用 `agent-computer observation urls --json` 或 `.agent\observation.urls.json` 拿到默认 observation 入口
5. Model 默认读取 `model_default_image_url`，也就是 latest grid image
6. 如需确认 freshness，再读取 `model_default_meta_url`
7. 如需读取当前鼠标坐标，再读取 `model_mouse_url`
8. 用 `click`、`scroll`、`paste`、`browser-open-url` 等原子动作执行业务步骤
9. 再次读取 latest grid image，并顺便读取下一步坐标
10. 如果点击之后没有出现预期结果，先读取当前鼠标坐标，并和 latest grid image 对照，优先确认是否存在坐标偏差
11. 不要因为一次点击失败或页面异常就停止，继续思考并尝试其他可行路径，直到用户需求完成
12. 如果出现手册中没有覆盖的新行为 -> 结果映射，把它追加回操作手册，并记录 URL、鼠标坐标和页面反馈
13. 只有当 latest grid image 看不清楚时，才临时使用 `capture-preview`
14. 只有当你需要冻结一张静态高精度网格图时，才使用 `capture-grid`

### 5.2 浏览器网页链路

适用场景：

- Chrome / Chromium 网页
- Browser Assist 扩展已连接
- 需要先做 DOM 几何定位，再做桌面点击的场景

默认推荐顺序：

1. 如果目标页面 URL 已知，先用 `browser-open-url`
2. 聚焦目标浏览器窗口，并确保目标窗口已经最大化
3. 确认 Browser Assist 已连接：
   使用 `browser-assist-status`
4. 用 `browser-assist-locate` 发送结构化定位请求
5. 从返回结果中读取 `mapped.screenCandidates[*].screenPoint`
6. 用 `click` 执行桌面点击
7. 点击后再读取 latest grid image，仅用于确认结果，而不是用于先定位

也就是说：

- 浏览器页面的默认定位来源是 Browser Assist
- `grid` 在这个链路里默认只负责看结果
- 只有 Browser Assist 失败或当前页面不适合插件定位时，才回退到纯 grid 读坐标

## 6. 便捷启动

项目根目录自带一个 Windows launcher：

```powershell
.\windows-launcher.ps1 browser-open-url --url "https://www.zhipin.com/"
.\windows-launcher.ps1 browser-current-url
.\windows-launcher.ps1 browser-assist-status
.\windows-launcher.ps1 browser-assist-locate --input-file .\docs\examples\browser-assist-request.json
.\windows-launcher.ps1 browser-back
.\windows-launcher.ps1 browser-forward
.\windows-launcher.ps1 browser-refresh
.\windows-launcher.ps1 maximize --title "Google Chrome"
.\windows-launcher.ps1 observation urls
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
/live/frame.jpg?token=<TOKEN>&mode=preview
/live/frame.jpg?token=<TOKEN>&mode=grid
/live/frame.json?token=<TOKEN>&mode=preview
/live/frame.json?token=<TOKEN>&mode=grid
/observation/latest.jpg?token=<TOKEN>&mode=grid
/observation/latest.json?token=<TOKEN>&mode=grid
/observation/mouse.json?token=<TOKEN>
```

默认角色分工：

- Human 默认看 `/live`
- Human 通过 `/live` 内部切换 `preview` / `grid`
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

## 8. Browser Assist Locator

项目提供一套 Browser Assist Locator v1 最小闭环：

- 扩展负责网页 DOM 几何定位
- daemon 负责 WebSocket 桥接与坐标映射
- `agent-computer` 继续负责实际桌面动作执行

Browser Assist 的后端入口：

```text
GET  /browser-assist/status
POST /browser-assist/locate
GET  /ws/browser-assist?token=<TOKEN>
```

Browser Assist 配置文件位于：

- `.agent\browser_assist.json`

扩展源代码位于：

- `extensions\browser-assist-locator`

打包扩展：

```powershell
.\scripts\package_browser_assist_extension.ps1
```

查看扩展连接状态：

```powershell
.\windows-launcher.ps1 browser-assist-status
```

执行 Browser Assist 定位：

```powershell
.\windows-launcher.ps1 browser-assist-locate --input-file .\docs\examples\browser-assist-request.json
```

请求体示例：

```json
{
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
```

Browser Assist 的输出边界：

- 插件返回 `page / viewport / browser / matches`
- 插件返回 `browser.contentLeftOnScreen` / `contentTopOnScreen`
- 插件不做 screen 坐标最终映射
- daemon 负责把 `clickablePoint` 映射成桌面绝对坐标

推荐浏览器操作链路：

1. `browser-open-url`
2. `browser-assist-status`
3. `browser-assist-locate`
4. 读取 `mapped.screenCandidates[*].screenPoint`
5. `click`
6. `observation/latest.*?mode=grid` 仅用于确认点击结果

也就是说：

- Browser Assist 负责“找在哪”
- daemon 负责“算到哪”
- `agent-computer click` 负责“点下去”
- `grid` 默认不再负责浏览器页面的前置定位，只负责事后验证

快速 roundtrip 检查：

```powershell
.\scripts\test_browser_assist_roundtrip.ps1
.\scripts\test_browser_assist_roundtrip.ps1 -RequestFile .\docs\examples\browser-assist-request.json
```
