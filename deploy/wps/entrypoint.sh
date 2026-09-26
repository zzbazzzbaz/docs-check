#!/bin/bash
# 无头环境准备（Xvfb / dbus / WPS 配置），然后执行传入的命令。详见 ../README.md
set -e

if [ ! -S /tmp/.X11-unix/X99 ]; then
    mkdir -p /tmp/.X11-unix
    Xvfb :99 -screen 0 1280x1024x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
    for _ in $(seq 1 50); do
        [ -S /tmp/.X11-unix/X99 ] && break
        sleep 0.2
    done
fi

mkdir -p "$XDG_RUNTIME_DIR"

mkdir -p /run/dbus
if [ ! -S /run/dbus/session ]; then
    dbus-daemon --session --fork --address="unix:path=/run/dbus/session" 2>/dev/null || true
fi

mkdir -p /root/.config/Kingsoft
cat > /root/.config/Kingsoft/Office.conf <<'CONF'
[General]
languages=zh_CN
AcceptedEULA=true
FirstRun=false
UpdateMode=manual
CloudServiceEnabled=false
[6.0]
common\AcceptedEULA=true
common\UserInfo\ACUPI=true
wpsoffice\Application%20Settings\AppComponentMode=prome_independ
wpsoffice\Application%20Settings\AppComponentModeInstall=prome_independ
plugins\officespace\flogin\enableForceLogin=false
CONF

exec "$@"
