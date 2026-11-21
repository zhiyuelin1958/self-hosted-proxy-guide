# iPhone 独立中继脚本

中继只在 VLESS 隧道内可达：手机连 `<SERVER_IP>:8443` 的请求经 Clash Mi 进入隧道，由主 Xray 的 `relay-private` 出站转给网络命名空间里的 Envoy。公网上 8443 没有监听。原理和验收见教程的防直连一章。

> 这些脚本来自一次实际可用的部署，公开前做了脱敏（改名、把 IP 和出站标签提到 `relay_settings.py`、去掉针对特定服务的检查）。**脱敏后未在新服务器上完整跑过**，第一次部署请逐步执行、逐步检查输出。

## 前提

- 主 Xray 运行正常，`/usr/local/etc/xray/config.json` 中有 tag 为 `exit2`（或你在设置里写的名字）的第二出口；
- Debian 12 / Ubuntu 24.04，x86_64，有 `python3`、`iptables`（含 `TPROXY` 模块）、`ip`、`ufw`；
- 防火墙**不要**放行 8443、18443、18445；80 只在申请和续期证书时临时放行。

## 文件

| 文件 | 作用 |
|---|---|
| `relay_settings.py` | 唯一需要编辑的文件：服务器 IP、端口、出站 tag、用户名 |
| `relay_config.py` | 生成 Envoy 配置：认证、CONNECT / CONNECT-UDP、下载路由 |
| `relay_network.py` | 由 systemd 调用：建立和拆除网络命名空间、veth、策略路由和 TPROXY 规则 |
| `prepare_relay.py` | 一次性准备：系统用户、目录、下载校验 Envoy、生成账号、写配置与 systemd 单元（不启动），输出要加进主 Xray 的出站和规则 |
| `enable_renewal.py` | 安装证书续期钩子与定时器，复制证书，启动 `app-relay.target` |
| `relay_certificate_hook.py` | 证书续期后复制新证书并重启 Envoy |
| `publish_profiles.py` | 按域名清单生成正式描述文件；`--publish` 时替换在线配置并重启中继 |

## 顺序

```bash
# 0. 在本机编辑 relay_settings.py，然后把本目录和域名清单传到服务器
scp -r server/relay root@<SERVER_IP>:~/relay
scp templates/protected-domains.example.json root@<SERVER_IP>:~/relay/protected-domains.json

# 以下在服务器 ~/relay 目录以 root 执行
python3 prepare_relay.py
# 把输出里 addToMainXray 的出站加进主 Xray，规则放在 routing.rules 第一条，然后：
XRAY_LOCATION_ASSET=/usr/local/share/xray xray run -test -config /usr/local/etc/xray/config.json && systemctl restart xray
# 申请 IP 证书（Certbot 5.4 以上，装在独立虚拟环境；申请期间临时放行 TCP 80）
python3 -m venv /opt/app-relay/acme && /opt/app-relay/acme/bin/pip install 'certbot>=5.4'
ufw allow 80/tcp
/opt/app-relay/acme/bin/certbot certonly --standalone --preferred-profile shortlived \
  --ip-address <SERVER_IP> --cert-name app-relay-ip -m <你的邮箱> --agree-tos
ufw delete allow 80/tcp
python3 enable_renewal.py
systemctl status app-relay.target app-relay-envoy.service app-relay-egress.service --no-pager
cat /var/lib/app-relay/credentials.json      # 测试描述文件地址：
#   https://<SERVER_IP>:8443/install/<downloadToken>/test.mobileconfig（开着 Clash Mi 在手机上打开）
# 手机装测试描述文件、验收通过后：
python3 publish_profiles.py            # 先只生成并校验
python3 publish_profiles.py --publish  # 正式发布，输出各用户下载地址
```

要把手机的 Clash Mi 配置也作为订阅分发：把文件放到 `/etc/app-relay/profiles/`，在 `/etc/app-relay/client-downloads.json` 里写 `{"/install/<随机令牌>/phone.yaml": "/etc/app-relay/profiles/phone.yaml"}`，再运行 `publish_profiles.py --publish`。

## 服务器端自检

经隧道测试时，在开着 Clash Mi 的电脑上执行（`--preproxy` 让去中继的连接先进隧道）：

```bash
# 未认证：应报 CONNECT tunnel failed, response 407
curl -sS --preproxy socks5h://127.0.0.1:3067 --proxy https://<SERVER_IP>:8443 https://www.cloudflare.com/cdn-cgi/trace
# 认证后经中继访问，应显示第二出口
curl -sS --preproxy socks5h://127.0.0.1:3067 --proxy https://user1:<密码>@<SERVER_IP>:8443 https://www.cloudflare.com/cdn-cgi/trace
```

在服务器上：

```bash
ss -ltn | grep ':8443'                       # 应无输出：公网不监听
systemctl stop app-relay-egress.service     # 故障演练：上面的认证请求应失败
systemctl start app-relay.target            # 恢复
```

## 停用与卸载

```bash
systemctl disable --now app-relay.target app-relay-renew.timer
```

再从主 Xray 删除 `relay-private` 出站和首条规则。停用后，已安装描述文件的手机访问名单内域名会失败，需在手机上移除描述文件。
