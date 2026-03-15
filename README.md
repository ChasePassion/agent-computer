# Agent Computer

一个给 Codex 直接调用的 Windows 桌面原子工具集。

## 0. Agent First Quickstart

推荐顺序如下：

```powershell
npx skills add https://github.com/ChasePassion/agent-computer-skill
git clone https://github.com/ChasePassion/agent-computer.git
cd agent-computer
Copy-Item .env.example .env
.\scripts\bootstrap.ps1
```

说明：

- 安装skill这一步依赖 `Node.js` / `npx`
- 如果当前机器没有 `npx`，先安装 Node.js 再继续
- 如果需要远程 live，把维护者私下提供的服务器信息填进 `.env`
- 出于安全原因，`.env` 不进 git，仓库只提供 `.env.example`

- 如果 `.env` **不配置远程相关项**，就继续走本地模式
- 如果 `.env` **配置了远程相关项**，observation / tunnel 会直接读取环境变量连接共享服务器
- relay host / user / password / public base URL 这类敏感信息只放在 `.env`，不再写入 `.agent/*.json`

bootstrap 完成后，常用命令是：

```powershell
.\windows-launcher.ps1 daemon start
.\windows-launcher.ps1 observation urls
```

这两个脚本的职责：

- `scripts/bootstrap.ps1`
  - 创建或更新 `.conda`
  - 执行 `pip install -e .`
  - 启动 daemon 并生成 observation URL
  - 不负责安装外部 skills

bootstrap 结束后会生成：

- `.agent/bootstrap.status.json`

agent 下次进入仓库时，可以先看这个文件判断本地是否已经初始化完成。敏感远程配置不会写入这个状态文件。

如果在运行 `bootstrap.ps1` 前已经在 `.env` 里写了下面这些值，后续脚本会直接从环境变量读取：

- `AGENT_COMPUTER_RELAY_HOST`
- `AGENT_COMPUTER_RELAY_USER`
- `AGENT_COMPUTER_RELAY_PORT`
- `AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL`
- 可选：`AGENT_COMPUTER_RELAY_SSH_PORT`
- 可选：`AGENT_COMPUTER_RELAY_PASSWORD`

## 0.0 直连共享服务器

推荐按照下面顺序执行：

1. 安装外部 skills
2. 拿到维护者单独提供的服务器信息
3. 把 `.env.example` 复制为 `.env`
4. 在 `.env` 中填写：

```powershell
AGENT_COMPUTER_RELAY_HOST=<relay host>
AGENT_COMPUTER_RELAY_USER=<relay user>
AGENT_COMPUTER_RELAY_PORT=<relay port>
AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL=<public base url>
AGENT_COMPUTER_RELAY_PASSWORD=<relay password>
```

5. 运行 `.\scripts\bootstrap.ps1`：

```powershell
.\scripts\bootstrap.ps1
```

6. 启动本地 daemon 和反向隧道：

```powershell
.\scripts\start_observation_local.ps1
.\scripts\start_observation_tunnel.ps1
.\scripts\show_observation_urls.ps1
```

如果设置了 `AGENT_COMPUTER_RELAY_PASSWORD`，隧道脚本会优先走仓库内置的非交互 Python/paramiko 模式，不必卡在 SSH 手动输密码。

最终 live 地址会是维护者提供的 `public_base_url`：

```text
<public_base_url>/live?token=...
```

## 0.1 帮用户上传 Browser Assist 插件

 `Browser Assist Locator`，你需要帮助用户完成 Chrome 扩展上传。

推荐流程：

### 第 1 步：确保技能和 daemon 已准备好

```powershell
npx skills add https://github.com/ChasePassion/agent-computer-skill
.\windows-launcher.ps1 daemon start
.\windows-launcher.ps1 browser-assist-status
```

如果这时返回 `connected: false`，属于正常，说明后端已经起来了，只是扩展还没有上传到 Chrome。

### 第 2 步：打开扩展页并帮助用户上传

目标页面：

```text
chrome://extensions/
```

推荐按这个顺序执行：

1. 打开 `chrome://extensions/`
2. 确保 Chrome 最大化
3. 开启右上角 `Developer mode`
4. 点击 `Load unpacked`
5. 在弹出的文件夹选择器中，选择：`extensions/browser-assist-locator`

### 第 3 步：帮用户确认扩展是否连接成功

```powershell
.\windows-launcher.ps1 browser-assist-status
```

成功时应出现：

- `connected: true`
- `extensionVersion`
- `browserName`
- `lastSeenAt`

如果仍未连接，推荐排障顺序：

1. 确认扩展已加载且开关开启
2. 确认浏览器是前台窗口
3. 回到 `chrome://extensions/` 点击 `Update`
4. 再次执行 `browser-assist-status`

### 第 4 步：正式使用 Browser Assist

```powershell
.\windows-launcher.ps1 browser-open-url --url "<目标 URL>"
.\windows-launcher.ps1 browser-assist-locate --input-file .\docs\examples\browser-assist-request.json
```

定位成功后，真正执行点击的仍然是：

```powershell
.\windows-launcher.ps1 click --x <screen_x> --y <screen_y>
```

也就是说：

- 扩展负责定位
- daemon 负责映射
- `agent-computer` 负责执行

### 第 5 步：代码更新后的扩展刷新

如果扩展代码改了，不需要重新走完整上传流程，优先这样做：

1. 回到 `chrome://extensions/`
2. 确保 `Developer mode` 开启
3. 点击 `Update`
4. 再次执行 `.\windows-launcher.ps1 browser-assist-status`

## 0.2 命令入口

源码安装完成后，命令入口是：

- `agent-computer`
- `agent-computer-daemon`

## 0.3 远程观察与服务器

当前 observation / live 的默认路径仍然是：

1. 本地启动 daemon
2. 如果需要公网访问，使用你已有服务器做反向代理和隧道
3. 通过以下脚本查看最终访问 URL：

```powershell
.\scripts\start_observation_local.ps1
.\scripts\start_observation_tunnel.ps1
.\scripts\show_observation_urls.ps1
```

现有纯桌面控制、Observation latest 与截图强化能力：

- Observation latest preview / grid
- 绝对坐标网格截图
- 轻量预览截图
- 通用截图
- 列出窗口 / 聚焦窗口
- 点击 / 双击 / 移动 / 滚动
- 键盘输入 / 粘贴 / 热键
- 浏览器 URL 直达导航

如果需要定位元素，推荐流程是：

1. 先确保 daemon 与 Observation Layer 已启动
2. Model 默认取 latest grid image，而不是直接看 `/live` 网页
3. 调用点击、滚动、输入等桌面动作
4. 再读取最新的 latest grid image，确认状态并顺便读取下一步坐标
5. 如此循环

只有在 latest image 看不清楚当前状态、或你需要冻结一张更高确定性的静态图时，才额外使用手动截图做兜底观察。
如果窗口没有最大化，或在截图与点击之间发生了分屏、缩放、尺寸变化，坐标命中率会明显下降。

补充约束：

- 如果目标站点的操作手册已经给出了目标信息，以手册为准
- 当操作没有出现预期行为的时候，首先应该认为是自己的定位不准确
- 在点击之后没有出现预期结果时，先获取当前鼠标坐标信息，再对照最新网格图片复核，优先排查是否因为坐标偏差导致点击没有落在目标上
- 每次对目标开始操作之前，首先阅读相关的 skill / 操作手册
- 思考一切可行办法去完成用户的需求；在用户需求被完成之前，不要因为单次失败、页面异常或路径不顺手就停止

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

### 3.1 浏览器导航命令

用于当前前台浏览器窗口的 URL 打开、URL 读取和前进后退控制：

```powershell
agent-computer browser-open-url --url "https://www.zhipin.com/"
agent-computer browser-open-url --url "https://www.zhipin.com/web/geek/jobs?city=101210100&query=agent%E5%BC%80%E5%8F%91" --restore-clipboard
agent-computer browser-current-url
agent-computer browser-back
agent-computer browser-forward
agent-computer browser-refresh
```

行为说明：

- `browser-open-url`：`Ctrl+L -> Ctrl+A -> paste URL -> Enter`
- `browser-current-url` 的行为是：校验前台窗口是浏览器，再执行 `Ctrl+L -> Ctrl+C -> Esc` 读取当前地址栏 URL
- `browser-back` 的行为是：`Alt+Left`
- `browser-forward` 的行为是：`Alt+Right`
- `browser-refresh` 的行为是：`Ctrl+R`

### 3.2 Browser Assist 插件命令

用于 Browser Assist Locator 扩展的打包、连接状态检查和结构化定位：

```powershell
.\scripts\package_browser_assist_extension.ps1
.\windows-launcher.ps1 browser-assist-status
.\windows-launcher.ps1 browser-assist-locate --input-file .\docs\examples\browser-assist-request.json
agent-computer browser-assist-status
agent-computer browser-assist-locate --input-file .\docs\examples\browser-assist-request.json
```

说明：

- `package_browser_assist_extension.ps1`：把扩展模板复制到产物目录，并把 `service_worker.js` 里的 WebSocket URL 替换成当前 daemon 的连接地址
- `browser-assist-status`：读取扩展连接状态，确认是否已经 `connected: true`
- `browser-assist-locate`：向扩展发送结构化 locate 请求，返回 `raw + mapped`
- 插件负责定位，daemon 负责 screen 映射，真实动作仍由 `click` / `type` / `scroll` 执行

### 3.3 Observation 命令与接口

Observation Layer 提供 live 页面、latest frame 和鼠标坐标读取：

- Human 默认入口：`/live?token=<TOKEN>`
- Human live frame 接口：`/live/frame.jpg?token=<TOKEN>&mode=preview|grid`
- Human live meta 接口：`/live/frame.json?token=<TOKEN>&mode=preview|grid`
- Model 默认入口：`/observation/latest.jpg?token=<TOKEN>&mode=grid`
- Model 默认元数据：`/observation/latest.json?token=<TOKEN>&mode=grid`
- latest preview 仍然保留给 Human 做纯净观察
- `latest.json` 会返回与当前 frame 对齐的 `mouse_position`
- `/observation/mouse.json` 提供当前鼠标的即时坐标
- `/observation/latest.*` 现在只支持 `mode=grid`，用于 AI / model 侧

```powershell
.\windows-launcher.ps1 observation urls
.\windows-launcher.ps1 observation urls --json
agent-computer observation urls --json
agent-computer observation mouse --json
```

### 3.4 截图命令

网格截图：

```powershell
agent-computer capture-grid
agent-computer capture-grid --grid-size 50 --jpeg-quality 90 --output .\artifacts\grid.jpg
```

预览截图：

```powershell
agent-computer capture-preview
agent-computer capture-preview --output .\artifacts\preview.jpg
```

通用截图：

```powershell
agent-computer capture --target primary-screen --format png
agent-computer capture --target active-window --format jpeg --jpeg-quality 70
agent-computer capture --window-title "Windows PowerShell" --grid
```

截图说明：

- `capture-grid`：整屏、高质量 JPEG、带绝对坐标网格
- `capture-preview`：整屏、压缩 JPEG、无网格
- `capture`：通用截图入口，可指定目标窗口、格式和网格
- 网格绘制使用四边标尺带，默认细线 `50px`，主线 `100px`
- 返回坐标始终是屏幕绝对坐标

### 3.5 窗口与鼠标动作命令

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

滚轮、输入、粘贴、按键、组合键：

```powershell
agent-computer scroll --amount -500
agent-computer type --text "hello world"
agent-computer paste --text "agent开发"
agent-computer paste --text "agent开发" --restore-clipboard
agent-computer press --key enter
agent-computer hotkey ctrl shift s
```

说明：

- `type` 适合 ASCII、快捷测试
- `paste` 更适合中文、长文本、复杂内容
- `paste` 的行为是：先把指定文本放进 Windows 剪贴板，再发送 `Ctrl+V`

## 4. 使用方式

默认推荐这样组合，而不是依赖手动截图主导的流程。

### 4.1 通用桌面链路

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

### 4.2 浏览器网页链路

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

## 5. 便捷启动

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

## 6. Observation Layer

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
.\scripts\start_observation_tunnel.ps1
.\scripts\show_observation_urls.ps1
```

## 7. Browser Assist Locator

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
    "hint": "当前职位详情区域里的收藏按钮"
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
