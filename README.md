# 从零自建代理节点：VLESS + REALITY、分流、二级出口与防直连

这是一份按实际部署整理的教程，敏感信息都已脱敏。按第 00～10 章做完，你会得到：

- 一台自己的海外服务器，运行 Xray（VLESS + REALITY + XTLS-Vision，TCP 443）；
- 电脑和手机上的客户端按规则模式分流：国内直连，其余走代理；
- 可选：服务器把指定服务的流量转给第二个出口（如某地的静态 IP），其余国际流量仍从服务器本身出去；
- 可选：防直连。客户端关掉时，指定服务的流量直接失败，不走本地网络；
- 一套可重复的测试与验收方法、备份与恢复脚本，以及记录计划、进度和测评的模板。

> 本仓库里的 IP、密钥、UUID 和账号都是占位符或文档专用地址。`203.0.113.0/24`、`198.51.100.0/24` 是 RFC 5737 保留给文档示例的网段，不指向任何真实主机。使用时换成你自己生成的值，**不要把真实值提交到公开仓库**。提交前的检查方法见[发布前自查](#发布前自查)。

## 整体架构

```text
电脑 / 手机：客户端（本文以 Karing 为例）规则模式
    ├─ 国内域名库 / 中国 IP 库 / 个人补充 ─────► 本地直连
    ├─ 校园网 / 局域网 / 私有地址 ────────────► 本地直连
    └─ 其余流量 ──► 入口服务器 <SERVER_IP>:443（VLESS+REALITY）
                         ├─ 普通国际流量 ──────► 入口服务器所在地出口
                         └─ 指定服务（可选）
                                  ↓
                         第二出口 <EXIT2_HOST>:<EXIT2_PORT>（SOCKS5）
```

| 部分 | 示例方案 | 可替换为 |
|---|---|---|
| 入口服务器 | 云厂商日本区，2 核 / 1 GiB / Debian 12 | 任意延迟低、线路稳的海外 VPS |
| 协议 | VLESS + REALITY + XTLS-Vision，TCP 443 | — |
| 第二出口（可选） | 某地 SOCKS5 静态 IP 代理 | 另一台 VPS、其他供应商 |
| 客户端 | Karing（Windows / iOS / Android / macOS） | 任何支持 sing-box 规则集的客户端 |
| 规则数据 | [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 的国内域名库与中国 IP 库 | — |

## 阅读路线

| 章节 | 内容 | 是否必做 |
|---|---|---|
| [00 原理速览](docs/00-原理速览.md) | 代理、TLS/SNI、REALITY、分流、DNS 各自解决什么问题 | 建议先读 |
| [01 准备与选型](docs/01-准备与选型.md) | 服务器地区与规格、费用与流量、客户端、要准备的东西 | 必做 |
| [02 创建服务器](docs/02-创建服务器.md) | 以 Azure 为例开机、SSH 密钥登录、云防火墙 | 必做 |
| [03 系统加固](docs/03-系统加固.md) | 禁 root/密码登录、ufw、fail2ban、自动安全更新、BBR | 必做 |
| [04 部署 Xray](docs/04-部署Xray-REALITY.md) | 安装、生成密钥、写配置、启动、生成导入链接 | 必做 |
| [05 客户端与分流](docs/05-客户端与分流.md) | Karing 导入节点、规则模式、分流组顺序、DNS、规则更新 | 必做 |
| [06 二级出口](docs/06-二级出口.md) | 服务端按域名/IP/端口把指定流量转给第二出口 | 可选 |
| [07 防直连](docs/07-防直连.md) | Windows 浏览器策略、iPhone 系统中继、命令行启动前检查 | 可选 |
| [08 测试与验收](docs/08-测试与验收.md) | 出口、DNS、WebRTC/STUN、故障隔离、速度、IP 质量解读 | 必做 |
| [09 维护、备份与恢复](docs/09-维护备份与恢复.md) | 流量与账单、快照/恢复、升级策略、开机自启 | 必做 |
| [10 故障排查](docs/10-故障排查.md) | 常见问题与定位顺序 | 遇到再看 |

做完后，复制 [templates/计划进度测评模板.md](templates/计划进度测评模板.md)，记下自己的方案、进度和测试结果。**这份记录会含真实密钥，只放在本地，不要提交**。

## 仓库结构

```text
docs/                         教程正文（00～10）
server/
  xray/config.basic.json      单出口配置（第 04 章）
  xray/config.chain.json      带第二出口的配置（第 06 章）
  scripts/gen-secrets.sh      一次生成 UUID、REALITY 密钥对、shortId
  scripts/make-vless-link.sh  拼出客户端导入链接
  scripts/xray-snapshot.py    服务器配置快照
  scripts/xray-restore.py     校验并恢复快照
  relay/                      iPhone 系统中继（第 07 章进阶，Envoy + Xray）
client/
  karing/routing-groups.example.json   分流组示例（打包成 zip 后导入）
  windows/browser-fail-closed.ps1      Chrome/Edge 防直连策略
  windows/check-traffic.bat            一键查看服务器流量
  wsl/wslconfig.example                WSL 镜像网络配置
  wsl/egress-guard.sh                  命令行工具启动前检查出口
  tools/stun_check.py                  检查 UDP/STUN 实际出口
templates/
  protected-domains.example.json       “指定服务”域名清单示例
  计划进度测评模板.md                    自己的记录模板
tools/check-secrets.sh                 提交前扫描疑似真实 IP / 密钥
```

## 发布前自查

如果你 fork 本仓库并写入自己的经验，提交前运行：

```bash
bash tools/check-secrets.sh
```

它会查找非文档网段的 IPv4、UUID、`vless://` 链接、疑似私钥和 `Proxy-Authorization` 头。脚本只是兜底，提交前仍要人工过一遍 `git diff --cached`。

## 声明

- 本教程面向个人自用的网络与隐私学习，请遵守你所在地的法律法规，以及云厂商、代理供应商和你所访问服务的使用条款。
- 不要把节点分享、转售给他人：既有法律风险，也会让流量和账单失控。
- 文中版本号、界面路径与测试数据来自 2026 年 11 月的一次部署，软件更新后可能变化，以官方文档为准。

## 许可证

[MIT](LICENSE)
