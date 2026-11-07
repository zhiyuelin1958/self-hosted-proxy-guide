# 04 部署 Xray（VLESS + REALITY + XTLS-Vision）

本章结束时，你会得到每位用户一行 `vless://` 链接，客户端导入即可用（先不做分流和二级出口）。

## 1. 安装 Xray

使用官方安装脚本，并指定版本，以便和客户端保持兼容组合（见第 09 章）：

```bash
sudo bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install --version v26.7.28
xray version
```

不加 `--version` 会安装最新版。安装后的位置：

| 内容 | 路径 |
|---|---|
| 程序 | `/usr/local/bin/xray` |
| 配置 | `/usr/local/etc/xray/config.json` |
| 规则数据 | `/usr/local/share/xray/geoip.dat`、`geosite.dat` |
| 服务 | `/etc/systemd/system/xray.service`（及 `xray.service.d/`） |

## 2. 生成密钥与标识

每样东西的作用：

| 名称 | 作用 | 谁持有 |
|---|---|---|
| UUID | 用户身份，每人一个 | 服务端 + 该用户的客户端 |
| REALITY 私钥 | 服务端用来认出自己的客户端 | **只在服务端** |
| REALITY 公钥 | 客户端用来完成握手（链接里的 `pbk`） | 客户端 |
| shortId | 额外的区分标识，0～16 位十六进制、偶数长度；可每人一个 | 服务端 + 客户端（链接里的 `sid`） |

一次生成两位用户所需的全部值（先把本仓库 `git clone` 到服务器，或用 `scp` 只传 `server/` 目录）：

```bash
bash server/scripts/gen-secrets.sh 2
```

或者手动：

```bash
xray uuid                 # 每位用户各执行一次
xray x25519               # 输出私钥和公钥
openssl rand -hex 4       # 每位用户各执行一次，得到 8 位 shortId
```

> `xray x25519` 的输出格式随版本变化：旧版显示 `Private key` / `Public key`；较新版本显示 `PrivateKey` / `Password`，其中 **`Password` 就是公钥**（客户端的 `pbk`），另外的 `Hash32` 行 REALITY 用不到。已知私钥时可用 `xray x25519 -i "<私钥>"` 重新算出公钥。

把这些值记到本地私密文件里。

## 3. 选择目标网站（SNI）

REALITY 会把未认证的连接转发给目标网站，所以这个网站要“像是你服务器会去连的样子”。选择标准：

1. 支持 **TLS 1.3** 和 **HTTP/2**；
2. 从你的服务器访问稳定、延迟低，最好在同一地区（日本服务器选日本常见大站）；
3. 不会把访问跳转到别的域名（`dest` 的域名和 `serverNames` 应一致）；
4. 避免和大量他人雷同的“热门教程示例”。

在服务器上检查候选网站：

```bash
xray tls ping <SNI_DOMAIN>
```

输出中应能看到 TLS 1.3、证书包含该域名。确定后记为 `<SNI_DOMAIN>`。

## 4. 写配置

把 [server/xray/config.basic.json](../server/xray/config.basic.json) 的内容复制到服务器，替换所有 `<...>` 占位符：

```bash
sudo cp /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.orig
sudo nano /usr/local/etc/xray/config.json
```

关键字段解释：

| 字段 | 含义 |
|---|---|
| `inbounds[0].port: 443` | 对外监听 443，和普通 HTTPS 一样 |
| `clients[].id` / `flow` | 每位用户的 UUID；`flow` 必须为 `xtls-rprx-vision` |
| `clients[].email` | 仅作标识，便于日志和统计区分用户 |
| `decryption: "none"` | VLESS 本身不加密（加密由 REALITY 负责） |
| `realitySettings.dest` | 目标网站 `域名:443`（新版也写作 `target`） |
| `serverNames` | 允许客户端使用的 SNI，填目标网站域名 |
| `privateKey` | 第 2 步生成的私钥 |
| `shortIds` | 允许的 shortId 列表 |
| `minClientVer` | 拒绝低于此版本的客户端内核（可选，见下文） |
| `sniffing` | 从流量中识别目标域名，第 06 章按域名分流时必需 |
| `routing` 中的 `geoip:private` → `block` | 禁止通过代理访问服务器所在内网（防止被当跳板） |
| `protocol: bittorrent` → `block` | 禁止 BT，避免版权投诉和流量暴涨 |

> 关于 `minClientVer`：它检查的是**客户端所用内核报告的 Xray 版本号**。基于 sing-box 的客户端报告方式与 Xray 客户端不同，设置过高会导致握手失败。本教程验证过 `"1.8.0"` 与 Karing 1.2.25 兼容；不确定时可以先不写这一项。

检查并启动：

```bash
sudo xray run -test -config /usr/local/etc/xray/config.json
sudo systemctl enable xray
sudo systemctl restart xray
systemctl is-active xray
sudo ss -tlnp | grep ':443'
```

`-test` 输出 `Configuration OK` 才重启；最后一行应看到 `xray` 在监听 443。

## 5. 生成客户端导入链接

链接格式（一行，无空格）：

```text
vless://<UUID>@<SERVER_IP>:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=<SNI_DOMAIN>&fp=chrome&pbk=<PUBLIC_KEY>&sid=<SHORT_ID>&type=tcp&headerType=none#<节点名>
```

| 参数 | 来源 |
|---|---|
| `sni` | 目标网站域名 |
| `fp=chrome` | 客户端模仿 Chrome 的 TLS 指纹 |
| `pbk` | REALITY 公钥（不是私钥） |
| `sid` | 该用户的 shortId |
| `#` 后 | 节点在客户端里显示的名字，如 `JP-User1` |

用脚本生成：

```bash
bash server/scripts/make-vless-link.sh <UUID> <SERVER_IP> <SNI_DOMAIN> <PUBLIC_KEY> <SHORT_ID> JP-User1
```

每位用户一条链接，分别私下发给对方。**链接里包含连接所需的全部信息，等同于密码**。

## 6. 快速验证

先在客户端导入链接（第 05 章第 1 节），选全局模式，访问：

- <https://www.cloudflare.com/cdn-cgi/trace>：`ip=` 应为 `<SERVER_IP>`，`loc=` 为服务器所在国家代码。

如果连不上，按顺序排查：

1. `systemctl status xray`、`journalctl -u xray -n 50` 有无报错；
2. 云安全组和 `ufw` 是否都放行了 443；
3. 链接中的 `pbk` 是否为公钥、`sid` 是否在服务端 `shortIds` 里、`sni` 是否在 `serverNames` 里；
4. 是否误设了过高的 `minClientVer`。

更多见[第 10 章](10-故障排查.md)。
