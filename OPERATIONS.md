# vRemoter 发布与运营手册

此文档是长期可复用的开发与发布操作单，不部署到公开官网。

## 1. 固定架构

```text
公开 GitHub vRemoter
  └─ 源码、设计与测试

Spaceship DNS
  ├─ vremoter.vincentstudio.org → 47.250.150.45
  └─ updates.vincentstudio.org  → 47.250.150.45

阿里云马来西亚 Ubuntu 24.04
  ├─ /srv/vincentstudio/vremoter-site/   官网
  └─ /srv/vincentstudio/updates/vremoter/
       ├─ releases.json
       ├─ commerce.json
       ├─ vRemoter-latest.pkg
       ├─ vRemoter-latest.dmg
       └─ 版本化 PKG / DMG
```

上海服务器备案完成后，可只修改 DNS 指向，APP 内 URL 不需要改变。

### 当前发布状态（2026-09-03）

- `https://vremoter.vincentstudio.org/` 已在马来西亚服务器通过 Caddy 提供服务。
- `https://updates.vincentstudio.org/vremoter/`、`releases.json` 与 `commerce.json` 已通过公网 HTTPS 和 CORS 验证。
- TLS 证书由 Caddy 自动申请和续期；首次证书为 Let's Encrypt。
- 待上传版本为 1.1.0：首次安装使用 PKG，已安装过驱动的用户可使用 DMG 只更新 APP。
- 1.1.0 新增 Chromecast Voice Remote、按型号保存的按键映射，以及可配置的豆包语音触发键。
- 更新清单必须最后替换，避免用户在安装包上传完成前收到新版本提示。
- APP 与官网购买入口已暂停；远程配置中没有启用且有效的店铺时，APP 自动隐藏入口。
- 当前 PKG 尚未完成 Developer ID 签名与公证，下载页必须保留明确提示；完成签名、公证和实机验证后再替换同版本文件或发布新版本。
- Spaceship 的根域名 A 记录仍指向上海服务器；本次只新增了 `vremoter` 和 `updates`，两者指向 `47.250.150.45`。
- GitHub 仓库为公开源码仓库，仓库主页与官网互相链接。

## 2. 首次部署

1. 服务器安装 Caddy，并开放 TCP 80、443。
2. 上传 `docs/` 内容到 `/srv/vincentstudio/vremoter-site/`。
3. 上传 `Server/releases.json` 与安装包到更新目录；若保留远程购买配置，再同步 `docs/config/commerce.json`。
4. 安装 `Server/Caddyfile`，运行 `caddy validate` 后 reload。
5. 在 Spaceship 增加 `vremoter`、`updates` 两条 A 记录。
6. 验证 HTTPS、CORS、移动端页面和中国大陆访问。

## 3. 远程购买配置（当前停用）

编辑公开更新目录中的 `commerce.json`：

- 修改 `stores[xiaohongshu].url`。
- 如二维码变化，替换 `xiaohongshu-qr.png` 并同步 `qrImageURL`。
- 更新 `updatedAt` 为当前 ISO 8601 时间。
- 用浏览器访问配置 URL，确认返回 JSON。
- 当前官网不读取此配置；APP 在没有有效店铺时隐藏购买入口。

公开目录只包含实际链接数据，不包含本手册。

## 4. 发布规则

### 首次安装或驱动变化

1. 更新 `Packaging/Info.plist` 版本号与构建号。
2. 运行测试、签名、公证和 `build-pkg.sh`。
3. 上传版本化 PKG，并更新 `vRemoter-latest.pkg`。
4. 在 `releases.json` 中将 `driver_update_required` 设为 `true`。

### 仅 APP 变化

1. 更新版本号与构建号。
2. 运行测试、签名、公证和 `build-dmg.sh`。
3. 同时保留 PKG 给首次安装用户，DMG 给已安装用户。
4. 在 `releases.json` 中将 `driver_update_required` 设为 `false`。
5. APP 自动更新优先选择 DMG；官网明确标注两者用途。

### 清单资产格式

```json
{
  "name": "vRemoter-1.1.0.dmg",
  "browser_download_url": "https://updates.vincentstudio.org/vremoter/vRemoter-1.1.0.dmg",
  "digest": "sha256:..."
}
```

发布前对每个文件执行 SHA-256，并把结果写入清单。

## 5. 回滚

- 不覆盖已发布的版本化安装包。
- `vRemoter-latest.pkg` 只是当前稳定版本的副本或软链接。
- 更新清单出错时，恢复上一个 `releases.json`。
- 官网出错时，恢复上一个网站目录快照并 reload Caddy。
- 小红书配置错误时，恢复上一个 `commerce.json`；客户端会继续使用最后一次成功缓存。

## 6. 发布前检查表

- [ ] GitHub 仓库为 Public，官网与仓库互相链接。
- [ ] `../marketing/` 未进入 Git 暂存区。
- [ ] APP 更新地址和购买配置地址为 `updates.vincentstudio.org`。
- [ ] 自测和 Release 构建通过。
- [ ] APP、驱动、PKG/DMG 签名与公证通过。
- [ ] BlackHole 驱动许可路线已解决。
- [ ] 新机器 PKG 首装通过。
- [ ] 旧机器 DMG 覆盖升级通过。
- [ ] 自动更新按驱动标记选择正确安装包。
- [ ] 官网、下载页、更新日志与二维码验证通过。
- [ ] Obsidian 项目档案已更新。
