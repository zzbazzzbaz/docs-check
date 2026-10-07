# deploy

开发期的 WPS 真值服务：让 WPS 自己算出文档的「有效格式」（字体 / 字号 / 对齐 / 缩进 / 行距 /
大纲级别 …），用来校验和校准审核规则。

**不是审核运行时的一环**——正式审核链路不依赖任何 office 渲染器。

## 文件

| 文件 | 作用 |
|---|---|
| `docker-compose.dev.yml` | WPS 常驻服务 |
| `wps/Dockerfile` | 镜像 |
| `wps/entrypoint.sh` | 入口：Xvfb / dbus / WPS 配置 |
| `wps/build.sh` | 下官方 deb + 构建 |

## 用法

```bash
cd deploy
./wps/build.sh                                  # 首次构建（会下 545MB 的 deb）
docker compose -f docker-compose.dev.yml up -d  # 起服务

# 取值（脚本由调用方挂载或拷入，镜像里没有）
docker compose -f docker-compose.dev.yml exec wps python3 /app/extract.py /in/x.docx
```

改过 `Dockerfile` / `entrypoint.sh` 之后：

```bash
docker compose -f docker-compose.dev.yml up -d --build --force-recreate
```

## 环境变量（可写进 `deploy/.env`，compose 自动读）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WPS_VER` | `12.1.2.28080` | build.sh 用的版本，决定 deb 文件名 |
| `WPS_DEB` | `wps-office_12.1.2.28080_amd64.deb` | compose 构建时传入 |
| `WPS_IMAGE` | `thesis-format-review/wps` | 镜像名 |
| `IMAGE_TAG` | `dev` | 镜像 tag |
| `WPS_IN_DIR` | `./data/in` | docx 输入目录，只读挂到 `/in` |
| `WPS_OUT_DIR` | `./data/out` | 结果输出目录，挂到 `/out` |
| `TZ` | `Asia/Shanghai` | 时区 |

## 为什么必须 amd64

WPS for Linux 只有 amd64 包，pywpsrpc 也只有 x86_64 轮子。Apple Silicon 上由 Docker Desktop 的
Rosetta 转译执行（实测 WPS 启动约 1 秒）。

构建时会报一条 `FromPlatformFlagConstDisallowed` 警告，是故意的：FROM 写死 amd64，
才不会在 arm64 机器上误建出「装不了 deb」的镜像。

## 官方 deb 从哪来

WPS 官方 CDN（`wps-linux-personal.wpscdn.cn`）对非浏览器请求一律 403，改用阿里云
UbuntuKylin partner 源：

```
https://mirrors.aliyun.com/ubuntukylin/pool/partner/wps-office_12.1.2.28080_amd64.deb
```

Maintainer 为 `wps_linux@kingsoft.com`，是官方包。

## 踩坑记录

### 安装 deb 前必须先建 `/home/wps`

WPS 的 postinst 会遍历 `/home/*` 取用户名，容器里没有 `/home` 用户时它退出码 1，
dpkg 跟着报错。目录必须在安装前就存在。

### 容器里没有 `pgrep`

debian-slim 不带 procps。最早的健康检查用 `pgrep -f 'Xvfb :99'`，退出码 127（unhealthy）。
现在用 X socket 文件 `/tmp/.X11-unix/X99` 判断；健康检查则直接起一次 WPS、确认 RPC 连得上。

### `docker exec` 不继承 entrypoint 的 `export`

常驻服务 + exec 调用最容易踩的一条：exec 起的进程只认镜像 `ENV`，不看 PID 1 的环境。
所以 `DISPLAY` / `XDG_RUNTIME_DIR` / `DBUS_SESSION_BUS_ADDRESS` 三个都写在 Dockerfile 的 `ENV` 里。

用 `docker run` 一次性执行不会有这个问题（入口直接 exec 命令，环境变量自然继承），
所以早期一直没暴露。

### dbus 必须用固定地址

原本用 `dbus-launch`，它生成临时地址，只有 entrypoint 的子进程知道，exec 进来的进程连不上。
改成 `dbus-daemon --address=unix:path=/run/dbus/session`，地址固定才能共享。

### 免 EULA / 多组件模式

`/root/.config/Kingsoft/Office.conf` 做三件事：

- `AcceptedEULA` / `FirstRun=false`：跳过首次运行界面
- `AppComponentMode=prome_independ`：多组件模式，pywpsrpc 连不上 WPS 进程时先查这里
- `enableForceLogin=false`：不登录云账号

另外 `chmod -x .../wpscloudsvr` 关掉云服务后台进程，无头环境用不到。

### 中文字体

取值读的是样式属性，理论上有无字体都一样；但缺字体时 WPS 的替换行为不好预料，
镜像里装了文泉驿正黑 / 微米黑兜底。

## 相关

- 三方对账（自研 vs aspose-words-foss vs WPS 真值）在 `../test2/`，WPS 侧直接复用这里的镜像。
- `deploy/wps/cache/`（deb）与 `deploy/data/`（运行数据）已在 `.gitignore` 里。
