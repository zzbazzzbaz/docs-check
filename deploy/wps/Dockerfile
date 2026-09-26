FROM --platform=linux/amd64 debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    QT_QPA_PLATFORM=offscreen \
    DISPLAY=:99 \
    XDG_RUNTIME_DIR=/tmp/runtime-root \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/run/dbus/session

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libc6 libfreetype6 libcups2 libglib2.0-0 libglu1-mesa libsm6 \
        libxrender1 libfontconfig1 libxext6 libxcb1 libbz2-1.0 libgl1 \
        libqt5core5a libqt5gui5 libqt5widgets5 libqt5xml5 libqt5dbus5 \
        libqt5network5 libqt5x11extras5 \
        xvfb dbus-x11 \
        bsdmainutils xdg-utils libxslt1.1 \
        python3 python3-pip \
        fonts-wqy-zenhei fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

ARG WPS_DEB=wps-office_12.1.2.28080_amd64.deb
COPY cache/${WPS_DEB} /tmp/wps.deb

# mkdir /home/wps：WPS 的 postinst 会遍历 /home/* 取用户名，没有 /home 用户时退出码 1
RUN apt-get update \
    && mkdir -p /home/wps \
    && apt-get install -y --no-install-recommends /tmp/wps.deb \
    && rm -f /tmp/wps.deb \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -x /opt/kingsoft/wps-office/office6/wpscloudsvr

RUN pip3 install --no-cache-dir --break-system-packages pywpsrpc

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-c", "import pywpsrpc.rpcwpsapi as m; print('pywpsrpc OK:', m.__file__)"]
