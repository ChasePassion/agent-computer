# Plan 3: Observation Layer / Live Preview v1

状态：已完成
创建日期：2026-03-13
完成日期：2026-03-13

## 1. 背景

当前 `agent-computer` 已具备：

- 本地 daemon
- 截图原子命令
- 桌面动作原子命令
- URL 导航与浏览器语义命令

但系统还缺少一层**持续观察能力**。

当前问题：

1. Human 无法在手机或外部浏览器持续看到桌面进度
2. Model / Codex 需要频繁主动触发截图，才能获得当前状态
3. `capture-preview` / `capture-grid` 只适合单次 snapshot，不适合“持续观察”
4. 缺少一套统一的“最新屏幕状态”接口

因此，需要在现有截图能力之上补一个独立的 **Observation Layer**。

## 2. 产品目标

本阶段只解决一件事：

**给 `agent-computer` 增加一套统一 Observation Layer，同时服务 Human 远程观察和 Model 获取 latest frame。**

目标能力：

1. Human 可以通过手机 / 浏览器远程查看当前桌面
2. Model 可以直接取当前最新一帧，而不是反复主动截图
3. Human 与 Model 共用同一套观察层
4. 支持 `Preview` 和 `Grid` 两种模式
5. 使用 12 位静态 token 做访问保护

## 3. 非目标

以下内容不属于 v1：

1. 不做账号密码体系
2. 不做 token 自动刷新
3. 不做 cookie / session 登录
4. 不做页面内远程控制
5. 不做音频
6. 不做 WebRTC / HLS / 复杂直播平台
7. 不做多用户权限系统
8. 不做公网高级安全体系
9. 不替代现有 snapshot 能力

说明：

- v1 的本质是“统一观察层”，不是“远程桌面控制系统”

## 4. 核心设计决策

### 4.1 采用方案 B：Human + Model 共用观察层

统一 Observation Layer 同时服务：

- Human：Live 页面
- Model：latest frame API

不拆两套系统。

原因：

1. 避免重复实现抓屏和缓存
2. Human / Model 使用的是同一时刻的屏幕状态
3. 降低后续维护成本

### 4.2 支持两种模式

模式定义：

- `preview`
  - 干净画面
  - 适合人看
- `grid`
  - 带坐标网格
  - 适合模型看

默认策略：

- Human 默认 `preview`
- Model 默认 `grid`

### 4.3 观察层以 latest frame 为中心，不以 stream 为中心

v1 不做真正的视频流协议。

内部模型：

1. 后台持续更新“最新帧”
2. Human 页面定时轮询最新帧
3. Model 直接取最新帧

这比做 MJPEG / WebSocket / WebRTC 更适合当前项目阶段。

### 4.4 Snapshot 保留，不被替代

保留现有命令：

- `capture-preview`
- `capture-grid`
- `capture`

角色分工：

- `Observation / latest`
  - 持续观察
  - 低延迟拿到当前状态
- `Snapshot`
  - 精确确认
  - 高质量静态图
  - 必要时强制新截图

## 5. 总体架构

### 5.1 新增组件

建议新增：

- `ObservationService`
- `routes_observation.py`
- `observation token` 持久化配置
- `latest frame` 文件与元数据缓存
- `live page` HTML

### 5.2 推荐目录结构

```text
src/agent_computer/
├─ services/
│  ├─ capture_service.py
│  ├─ navigation_service.py
│  ├─ session_service.py
│  └─ observation_service.py
├─ api/
│  ├─ app.py
│  ├─ routes_capture.py
│  ├─ routes_navigation.py
│  ├─ routes_actions.py
│  └─ routes_observation.py
├─ models/
│  ├─ requests.py
│  └─ responses.py
└─ runtime.py
```

### 5.3 运行形态

Observation Layer 跟随 daemon 一起运行：

1. daemon 启动
2. `ObservationService` 初始化
3. 后台线程定时更新 `preview` / `grid` latest frame
4. API 与 Live 页面读取最新缓存

## 6. Observation 数据模型

### 6.1 Latest Frame 结构

每种模式各维护一份 latest frame 状态：

```json
{
  "mode": "grid",
  "image_path": "artifacts/observation/grid_latest.jpg",
  "width": 1920,
  "height": 1080,
  "updated_at": "2026-03-13T15:42:18+08:00",
  "frame_seq": 128,
  "content_type": "image/jpeg",
  "grid_enabled": true
}
```

### 6.2 Session 扩展

建议扩展 `SessionService`：

- `_observation_state`
- `set_latest_frame(mode, payload)`
- `get_latest_frame(mode)`

这样：

1. `/system/health` 可附带最新观察状态摘要
2. 后续可以统一暴露最近更新时间、最近帧路径等

## 7. 最新帧生成策略

### 7.1 推荐策略：后台持续刷新 latest frame

新增后台循环：

- 默认间隔：`1.0s`
- 每轮刷新：
  - 更新 `preview_latest.jpg`
  - 更新 `grid_latest.jpg`
  - 更新对应 meta

### 7.2 v1 实现方式选择

本方案明确选择：

**方案 B：一次抓屏，派生两种模式**

不再保留 v1 采用方案 A 的讨论空间。

#### 方案 B：正式方案

在 `capture.py` 中补一个更底层的“抓一张原始屏幕图再派生两种模式”的能力。

流程：

1. 抓一张 primary-screen 原始图
2. 直接保存为 preview latest
3. 在同一张图上叠加网格，生成 grid latest

优点：

- 同一时刻的 preview / grid 对齐
- 只抓屏一次
- CPU 与 IO 更可控

结论：

- v1 直接按方案 B 实现
- 不走“两次抓屏”的过渡方案

### 7.3 文件写入策略

不要每一帧都生成带时间戳的新文件。

应使用固定 latest 文件：

- `artifacts/observation/preview_latest.jpg`
- `artifacts/observation/grid_latest.jpg`
- `artifacts/observation/preview_latest.jpg.meta.json`
- `artifacts/observation/grid_latest.jpg.meta.json`

写入方式：

1. 先写临时文件
2. 再原子替换到 latest 文件

这样可避免浏览器和模型读到半写入文件。

## 8. 自动清理机制

Observation Layer 引入持续抓图后，必须同时引入自动清理机制。

否则：

1. `artifacts` 会持续膨胀
2. 调试文件和 latest 文件会混在一起
3. 长时间运行后会产生大量无价值图片

### 8.1 清理目标

需要区分 3 类图片：

1. `latest` 文件
2. `snapshot` 文件
3. 临时文件

#### A. latest 文件

例如：

- `artifacts/observation/preview_latest.jpg`
- `artifacts/observation/grid_latest.jpg`

策略：

- 永远保留
- 每轮覆盖更新
- 不参与历史清理

#### B. snapshot 文件

例如现有：

- `artifacts/preview_*.jpg`
- `artifacts/grid_*.jpg`
- `artifacts/capture_*.png`
- 其他人工调试截图

策略：

- 保留最近一批
- 超过阈值后自动清理旧文件

#### C. 临时文件

例如：

- `*.tmp`
- `*.part`
- 原子替换前的临时输出

策略：

- 每次 ObservationService 启动时清理
- 每轮刷新结束后顺手清理超时残留

### 8.2 清理范围

建议只清理以下路径：

- `artifacts/observation/`
- `artifacts/` 中符合截图命名规则的文件

不应清理：

- 手工命名的其他业务文件
- `.agent/`
- 非截图类文档和调试数据

### 8.3 v1 清理规则

推荐采用“数量上限 + 时间上限”双规则。

#### Observation latest

- `preview_latest.jpg`
- `grid_latest.jpg`
- 对应 meta

规则：

- 永久保留最新文件

#### Snapshot 历史

建议保留：

- 最近 `200` 个 snapshot 文件
- 且只保留最近 `7` 天

执行逻辑：

1. 先按时间删除超过 `7` 天的旧截图
2. 再按修改时间排序
3. 如果数量仍超过 `200`，继续删除最旧文件

### 8.4 为什么要双规则

只按数量清理的问题：

- 低频使用时，旧文件可能无限保留很久

只按时间清理的问题：

- 高频使用时，短时间内也可能爆出大量文件

所以推荐：

- 时间限制控制“老垃圾”
- 数量限制控制“高频爆量”

### 8.5 建议实现位置

新增一个独立清理器，而不是把清理逻辑散落在各个 service 里。

建议：

- `src/agent_computer/services/artifact_retention.py`

提供接口：

- `cleanup_observation_artifacts()`
- `cleanup_snapshot_artifacts()`
- `cleanup_temp_artifacts()`

如果不单独拆文件，至少也应在 `ObservationService` 内部做成独立私有方法：

- `_cleanup_latest_temp_files()`
- `_cleanup_snapshot_history()`

### 8.6 触发时机

推荐 3 个触发点：

1. daemon / ObservationService 启动时
2. Observation 后台刷新线程每隔一段时间
3. 手动 snapshot 成功后

建议频率：

- `latest` 临时文件清理：每轮都可做轻量清理
- `snapshot` 历史清理：每 `60` 轮或每 `5` 分钟执行一次

### 8.7 清理安全策略

为避免误删，应增加这些约束：

1. 只删除符合命名规则的截图文件
2. 只删除位于允许目录下的文件
3. latest 当前文件永不删除
4. meta 文件与图片文件一并成对删除

### 8.8 命名规则建议

为了让自动清理安全，建议统一 Observation / Snapshot 的命名规则：

Observation：

- `preview_latest.jpg`
- `grid_latest.jpg`

Snapshot：

- `preview_YYYYMMDD_HHMMSS.jpg`
- `grid_YYYYMMDD_HHMMSS.jpg`
- `capture_YYYYMMDD_HHMMSS.png`

这样清理器可以稳定匹配，而不是靠“删除整个目录”。

### 8.9 状态可观测性

建议在 `/system/health` 或 observation status 中补充：

- 最近一次清理时间
- 当前 observation 目录文件数
- 当前 snapshot 文件数

这能帮助后续定位磁盘膨胀问题。

## 9. 认证与配置

### 9.1 Token 方案

采用静态 token：

- 长度：12
- 字符集：大写字母 + 数字
- 长期有效
- 不自动轮换

示例：

- `A7K9M2Q8ZT4P`

### 9.2 Token 持久化位置

建议放在：

- `.agent/observation.json`

建议结构：

```json
{
  "token": "A7K9M2Q8ZT4P",
  "created_at": "2026-03-13T15:30:00+08:00"
}
```

### 9.3 Token 初始化策略

daemon 启动时：

1. 检查 `.agent/observation.json`
2. 若不存在，则自动生成 token 并写入
3. 若存在，则直接复用

### 9.4 URL 传递方式

所有 Observation 相关路由统一支持：

- `?token=...`

原因：

1. 手机打开方便
2. 复制链接方便
3. 不引入额外登录态

### 9.5 安全边界说明

v1 明确接受以下事实：

1. URL query token 会出现在浏览器历史中
2. 可能出现在代理日志中
3. 不适合高安全公网场景

这与产品非目标一致。

## 10. 远程访问方案

### 10.1 设计目标

远程访问方案必须同时满足：

1. 易于配置
2. 易于启动
3. 不要求用户手工拼太多命令
4. 不要求把桌面机直接暴露到公网
5. 能稳定给手机浏览器一个固定访问地址

也就是说，v1 不只是“理论上支持公网”，而是要提供一条**默认推荐、容易落地的公网访问路径**。

### 10.2 默认推荐架构

默认推荐：

**桌面机本地 daemon + 公网服务器反向代理 + 反向隧道**

结构如下：

```text
手机浏览器
   ->
公网地址 / 域名
   ->
Nginx / Caddy
   ->
反向隧道
   ->
桌面机本地 agent-computer daemon
```

推荐原因：

1. 桌面机不需要直接开放公网端口
2. 公网入口稳定
3. 手机访问路径简单
4. 与当前 daemon 架构兼容
5. 比“桌面机直接 bind 0.0.0.0 暴露端口”更稳

### 10.3 应用层能力

应用层只负责：

1. 支持 host 绑定非 localhost
2. 提供 token 鉴权

当前 daemon 已支持 `host` 参数，见现有 `daemon.py` 结构，因此 Observation Layer 不需要另起服务。

### 10.4 对外访问策略

支持方式：

1. 公网 IP + 端口映射
2. 反向代理到稳定域名
3. 隧道 / 内网穿透工具给出稳定地址

Observation Layer 本身不关心外部入口来自哪一种。

### 10.5 默认建议

默认建议分两层：

#### 桌面机

- daemon 监听 `127.0.0.1`
- 不直接暴露公网

#### 公网入口

- 用 Nginx 或 Caddy 提供 `http://` / `https://` 入口
- 由反向隧道把请求转回桌面机 daemon

推荐默认值：

- 桌面机 daemon：`127.0.0.1:37688`
- 公网机回环端口：`127.0.0.1:437688`

### 10.6 最小配置项

为了做到“易于配置”，建议把公网访问只压缩成少量配置。

建议 Observation Layer / 部署层只关心这些变量：

```text
AGENT_COMPUTER_HOST=127.0.0.1
AGENT_COMPUTER_PORT=37688
AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL=https://example.com
AGENT_COMPUTER_OBSERVATION_RELAY_HOST=<public-host>
AGENT_COMPUTER_OBSERVATION_RELAY_USER=<user>
AGENT_COMPUTER_OBSERVATION_RELAY_PORT=437688
```

说明：

- `AGENT_COMPUTER_HOST` / `AGENT_COMPUTER_PORT`
  - 本地 daemon 监听地址
- `AGENT_COMPUTER_OBSERVATION_PUBLIC_BASE_URL`
  - live 页面向 Human 展示的公网访问前缀
- `AGENT_COMPUTER_OBSERVATION_RELAY_HOST`
  - 反向隧道目标机器
- `AGENT_COMPUTER_OBSERVATION_RELAY_USER`
  - 远程登录用户
- `AGENT_COMPUTER_OBSERVATION_RELAY_PORT`
  - 公网机侧回环映射端口

### 10.7 启动必须简单

为了满足“易于启动”，v1 应交付**脚本和模板**，而不是只给文档说明。

建议新增：

```text
scripts/
├─ start_observation_local.ps1
├─ start_observation_tunnel.ps1
└─ show_observation_urls.ps1

deploy/
└─ nginx/
   └─ agent-computer-observation.conf.example
```

各文件职责：

#### `scripts/start_observation_local.ps1`

职责：

1. 启动本地 daemon
2. 确保 ObservationService 启动
3. 默认监听 `127.0.0.1`

用户目标：

- 在桌面机上一条命令起 observation 服务

#### `scripts/start_observation_tunnel.ps1`

职责：

1. 读取 relay 配置
2. 启动反向 SSH 隧道
3. 自动把公网机 `127.0.0.1:<relay_port>` 转到本地 daemon

用户目标：

- 在桌面机上一条命令起公网访问隧道

#### `scripts/show_observation_urls.ps1`

职责：

1. 读取当前 token
2. 读取 `public_base_url`
3. 打印可直接给手机访问的完整链接

输出示例：

```text
Preview Live:
https://example.com/live?token=A7K9M2Q8ZT4P

Grid Latest:
https://example.com/observation/latest.jpg?token=A7K9M2Q8ZT4P&mode=grid
```

用户目标：

- 不需要手工拼接 URL

#### `deploy/nginx/agent-computer-observation.conf.example`

职责：

1. 提供现成 Nginx 反代模板
2. 直接转发 `/live`
3. 直接转发 `/observation/`

用户目标：

- 复制模板后仅改域名 / 端口即可

### 10.8 推荐运维约束

为了让“易启动”成立，建议 v1 明确以下约束：

1. 默认使用 SSH key，不使用密码写死在脚本里
2. 反向隧道默认目标是公网机回环地址，不直接绑公网地址
3. Live 页面与 latest 接口统一走同一个公网前缀
4. 不要求用户手动查 token 文件后再自己拼链接

### 10.9 示例启动路径

理想用户流程应被压缩成下面几步：

#### 桌面机首次配置

1. 配置 `.agent/observation.json`
2. 配置 relay host / user / public base url
3. 放好 SSH key

#### 日常启动

1. `.\scripts\start_observation_local.ps1`
2. `.\scripts\start_observation_tunnel.ps1`
3. `.\scripts\show_observation_urls.ps1`

然后用户直接把输出 URL 发到手机浏览器打开。

### 10.10 直接公网暴露为什么不作为默认方案

虽然 daemon 可以直接绑定 `0.0.0.0`，但不建议把它作为默认方案。

原因：

1. 桌面机暴露公网端口更脆弱
2. 家宽 / NAT / 动态 IP 场景更麻烦
3. 手机访问地址不稳定
4. 反向代理和隧道更容易统一部署

因此：

- `0.0.0.0` 作为可选方案保留
- 反向隧道 + 反向代理作为默认推荐方案

## 11. API 设计

### 11.1 Human Live 页面

建议路由：

- `GET /live?token=...`

行为：

1. 校验 token
2. 返回 HTML 页面
3. 默认模式为 `preview`

### 11.2 Latest Frame 图片接口

建议路由：

- `GET /observation/latest.jpg?token=...&mode=preview`
- `GET /observation/latest.jpg?token=...&mode=grid`

行为：

1. 校验 token
2. 读取对应 latest 文件
3. 返回 `image/jpeg`

说明：

- mode 默认值建议：
  - Human 页面内部默认 `preview`
  - API 默认 `grid`

### 11.3 Latest Frame 元数据接口

建议路由：

- `GET /observation/latest.json?token=...&mode=grid`

返回：

```json
{
  "mode": "grid",
  "image_url": "/observation/latest.jpg?token=...&mode=grid&ts=1710312345",
  "updated_at": "2026-03-13T15:42:18+08:00",
  "width": 1920,
  "height": 1080,
  "frame_seq": 128
}
```

用途：

- 给 model 看最新帧
- 给 Live 页面刷新状态条

### 11.4 可选状态接口

如果想让页面更轻一点，也可以拆成：

- `GET /observation/status?token=...`

返回：

- 当前模式
- 最近更新时间
- 当前分辨率

但 v1 不强制独立拆分，`latest.json` 已足够。

### 11.5 可选访问信息接口

为了降低配置和启动成本，建议补一个轻量访问信息接口：

- `GET /observation/access-info`

作用：

1. 返回当前 token
2. 返回本地访问 URL
3. 若配置了 `public_base_url`，返回公网访问 URL

返回示例：

```json
{
  "token": "A7K9M2Q8ZT4P",
  "local_live_url": "http://127.0.0.1:37688/live?token=A7K9M2Q8ZT4P",
  "public_live_url": "https://example.com/live?token=A7K9M2Q8ZT4P",
  "public_grid_latest_url": "https://example.com/observation/latest.jpg?token=A7K9M2Q8ZT4P&mode=grid"
}
```

说明：

- 这个接口对易用性帮助很大
- 也可以被 `show_observation_urls.ps1` 复用

## 12. Live 页面设计

### 12.1 页面元素

页面只保留 3 块：

1. 顶部轻量状态条
2. 模式切换按钮
3. 当前最新画面

### 12.2 状态条字段

建议展示：

- 当前模式
- 最近更新时间
- 当前分辨率

### 12.3 模式切换

页面内提供两个按钮：

- `Preview`
- `Grid`

点击后：

1. 更新前端当前 mode
2. 刷新图片 URL
3. 刷新状态条

### 12.4 不加入控制按钮

明确不做：

- 点击屏幕控制桌面
- 输入文字
- 滚轮控制
- 发送命令

Live 页是纯观察页。

## 13. 前端刷新机制

### 13.1 推荐用轮询

v1 建议用最简单的浏览器轮询：

1. 页面每 `1000ms` 拉一次 `latest.json`
2. 若 `frame_seq` 变化，再更新 `<img>` 的 `src`
3. `src` 加时间戳参数防缓存

示例：

```text
/observation/latest.jpg?token=...&mode=preview&ts=1710312345
```

### 13.2 为什么不用 WebSocket / MJPEG

因为 v1 目标不是高帧率直播，而是：

- Human 看当前进度
- Model 取 latest frame

轮询：

1. 实现简单
2. 与现有 daemon 结构兼容
3. 调试成本低
4. 对移动端也足够

## 14. Model 侧接入方案

### 14.1 默认接口

Model 直接取：

- `GET /observation/latest.json?token=...&mode=grid`

或直接拿图片：

- `GET /observation/latest.jpg?token=...&mode=grid`

### 14.2 模式切换

Model 需要纯净图时：

- `mode=preview`

默认仍然建议：

- `mode=grid`

### 14.3 Snapshot 保留

当 model 需要高质量强制确认时，继续使用：

- `capture-preview`
- `capture-grid`

Observation Layer 不替代这些接口。

## 15. 代码落点

### 15.1 runtime.py

文件：

- `src/agent_computer/runtime.py`

新增：

- `OBSERVATION_DIR`
- `observation_token_path()`
- `preview_latest_path()`
- `grid_latest_path()`
- `observation_remote_config_path()`

### 15.2 SessionService

文件：

- `src/agent_computer/services/session_service.py`

新增：

- latest frame 状态缓存
- observation token 摘要缓存
- 清理状态摘要缓存

### 15.3 ObservationService

文件：

- `src/agent_computer/services/observation_service.py`

职责：

1. 初始化 token
2. 管理后台刷新线程
3. 生成 / 更新 latest frame
4. 返回 latest frame 元数据
5. 调度自动清理任务

建议接口：

- `start()`
- `stop()`
- `ensure_token()`
- `latest(mode)`
- `latest_image_path(mode)`
- `render_live_page(token, mode)`
- `cleanup_if_needed()`

### 15.4 API

文件：

- `src/agent_computer/api/routes_observation.py`

新增路由：

- `GET /live`
- `GET /observation/latest.jpg`
- `GET /observation/latest.json`
- `GET /observation/access-info`

### 15.5 app.py

文件：

- `src/agent_computer/api/app.py`

需要修改：

1. 挂载 `routes_observation`
2. lifespan 中初始化 ObservationService
3. daemon 关闭时停止后台线程

### 15.6 registry.py

文件：

- `src/agent_computer/services/registry.py`

新增：

- `observation: ObservationService`

### 15.7 README

文件：

- `README.md`

新增内容：

1. Observation Layer 说明
2. `live` 页面用法
3. token 生成与访问示例
4. 对外访问说明
5. 一键启动脚本说明

### 15.8 Artifact Retention

新增：

- `src/agent_computer/services/artifact_retention.py`

职责：

1. 清理 observation 临时文件
2. 清理 snapshot 历史文件
3. 控制保留上限

### 15.9 Scripts / Deploy 模板

新增：

- `scripts/start_observation_local.ps1`
- `scripts/start_observation_tunnel.ps1`
- `scripts/show_observation_urls.ps1`
- `deploy/nginx/agent-computer-observation.conf.example`

## 16. 认证实现方案

### 16.1 简单依赖注入校验

建议在 `routes_observation.py` 里写一个依赖：

- `require_observation_token`

逻辑：

1. 从 query 读取 `token`
2. 与 ObservationService 当前 token 比较
3. 不匹配则返回 `401`

### 16.2 不污染现有本地原子命令

token 校验只作用于：

- `live`
- `observation/latest*`

不作用于当前本地 CLI / daemon 内部调用的桌面控制接口。

## 17. 实施步骤

### Step 1: 运行时目录与 token 持久化

完成：

- observation 目录
- token 文件
- token 初始化

### Step 2: ObservationService 基础骨架

完成：

- latest frame 状态模型
- start / stop
- latest 元数据访问

### Step 3: latest frame 刷新线程

完成：

- 后台定时生成 preview / grid latest
- 原子替换写入

### Step 4: 自动清理机制

完成：

1. latest 临时文件清理
2. snapshot 历史清理
3. 时间上限与数量上限双规则
4. latest 文件排除保护

### Step 5: Observation API

完成：

- `GET /live`
- `GET /observation/latest.jpg`
- `GET /observation/latest.json`

### Step 6: Live 页面

完成：

- 轻量 HTML
- mode 切换
- 状态条
- 定时轮询刷新

### Step 7: app / registry 接入

完成：

- daemon 启动自动启 observation
- 关闭时安全停止

### Step 8: 文档与使用说明

完成：

- README 示例
- 远程访问说明
- 启动脚本与代理模板

### Step 9: 易启动交付

完成：

1. 本地启动脚本可直接运行
2. 隧道启动脚本可直接运行
3. 可打印完整可访问 URL
4. Nginx 模板可直接复制使用

## 18. 验收标准

满足以下条件即视为 v1 完成：

1. daemon 启动后会持续维护 `preview` / `grid` 两份 latest frame
2. 手机或浏览器可通过 `/live?token=...` 访问
3. 页面默认 `preview`
4. 页面可切换到 `grid`
5. 页面有轻量状态条
6. 页面没有远程控制按钮
7. Model 可通过 latest 接口默认拿到 `grid`
8. Snapshot 命令仍然可用
9. token 为 12 位大写字母 + 数字
10. token 长期有效，重启后不变化
11. 提供本地启动脚本
12. 提供远程隧道启动脚本
13. 提供代理配置模板
14. 用户不需要手工拼接 live URL
15. latest 文件不会无限累积
16. snapshot 文件有自动清理策略
17. 临时文件不会长期残留

## 19. 风险与处理

### 风险 1：后台持续抓屏开销偏高

处理：

- v1 默认 1fps
- 如需要再开放刷新间隔配置
- 优先考虑“一次抓屏派生两种模式”

### 风险 2：latest 文件被读到半写入状态

处理：

- 使用临时文件 + 原子替换

### 风险 3：公网暴露安全较弱

处理：

- v1 接受静态 token 方案
- README 明确安全边界

### 风险 4：远程访问配置过于复杂

处理：

- 提供默认推荐架构
- 提供脚本与代理模板
- 把用户配置项压缩到最少

### 风险 5：运维人员把密码写进脚本

处理：

- 文档明确要求使用 SSH key
- 不在模板中保存密码

### 风险 6：浏览器缓存导致画面不刷新

处理：

- 图片 URL 附加时间戳参数

### 风险 7：daemon 退出后后台线程泄漏

处理：

- 在 lifespan shutdown 阶段显式 stop

## 20. 结论

这版 Observation Layer 的本质是：

**在现有 snapshot 工具集之外，增加一层统一的持续观察能力。**

它不是直播平台，也不是远程控制系统，而是：

- Human 默认看 `preview`
- Model 默认取 `grid`
- 双方共用同一套 latest frame 缓存
- 用静态 token 做轻量保护

这条路径与当前 `agent-computer` 的 daemon 架构高度兼容，也是当前阶段实现成本最低、收益最高的方案。
