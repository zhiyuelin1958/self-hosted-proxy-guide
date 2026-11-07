# iPhone 独立中继脚本

配合 [docs/07-防直连.md](../../docs/07-防直连.md) 第 3 节使用。原理、架构图和验收方法都在那里，这里只列文件和顺序。

> 这些脚本来自一次实际可用的部署，公开前做了机械化的脱敏（改名、把 IP 和出站标签提到 `relay_settings.py`、去掉针对特定服务的检查）。**改名后未在新服务器上重新完整跑过**，第一次部署请逐步执行、逐步检查输出。

## 前提

- 已完成第 04、06 章：主 Xray 运行正常，`/usr/local/etc/xray/config.json` 中有 tag 为 `exit2`（或你在设置里写的名字）的第二出口；
- Debian 12 / Ubuntu 24.04，x86_64，有 `python3`、`iptables`（含 `TPROXY` 模块）、`ip`；
- 云安全组和 `ufw` 能放行 80、8443；**不要**放行 18445、18443。

## 文件

| 文件 | 作用 |
|---|---|
| `relay_settings.py` | 唯一需要编辑的文件：服务器 IP、端口、出站 tag、用户名 |
| `relay_config.py` | 生成 Envoy 配置：认证、CONNECT / CONNECT-UDP、描述文件下载路由 |
| `relay_network.py` | 由 systemd 调用：建立/拆除网络命名空间、veth、策略路由和 TPROXY 规则 |
| `prepare_relay.py` | 一次性准备：系统用户、目录、下载校验 Envoy、生成账号、写配置与 systemd 单元（不启动） |
| `enable_renewal.py` | 安装证书续期钩子与定时器，复制证书，启动 `app-relay.target` |
| `relay_certificate_hook.py` | 证书续期后复制新证书并重启 Envoy |
| `publish_profiles.py` | 按保护名单生成正式描述文件；`--publish` 时替换在线配置并重启中继 |

## 顺序

```bash
# 0. 在本机编辑 relay_settings.py，然后把本目录和保护名单传到服务器
scp -r server/relay azureuser@<SERVER_IP>:~/relay
scp templates/protected-domains.example.json azureuser@<SERVER_IP>:~/relay/protected-domains.json

# 以下在服务器 ~/relay 目录执行
sudo python3 prepare_relay.py
sudo ufw allow 80/tcp && sudo ufw allow 8443/tcp      # 云安全组也要放行
# 申请 IP 证书（见 docs/07），然后：
sudo python3 enable_renewal.py
systemctl status app-relay.target app-relay-envoy.service app-relay-egress.service --no-pager
sudo cat /var/lib/app-relay/credentials.json            # 拼出测试描述文件下载地址：
#   https://<SERVER_IP>:8443/install/<downloadToken>/test.mobileconfig
# 手机装测试描述文件、验收通过后：
sudo python3 publish_profiles.py            # 先只生成并校验
sudo python3 publish_profiles.py --publish  # 正式发布，输出各用户下载链接
```

## 服务器端自检

```bash
# 未认证：应报 CONNECT tunnel failed, response 407
curl -sS --proxy https://<SERVER_IP>:8443 https://www.cloudflare.com/cdn-cgi/trace
# 认证后经中继访问，应显示第二出口
curl -sS --proxy https://user1:<密码>@<SERVER_IP>:8443 https://www.cloudflare.com/cdn-cgi/trace
# 故障演练：停掉中继出站，上一条应失败；然后恢复
sudo systemctl stop app-relay-egress.service
sudo systemctl start app-relay.target
```

## 停用与卸载

```bash
sudo systemctl disable --now app-relay.target app-relay-renew.timer
sudo ufw delete allow 8443/tcp
```

停用后，已安装描述文件的 iPhone 访问名单内域名会失败，需在手机上移除描述文件。
