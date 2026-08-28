# vRemoter 发布与运营手册（内部）

此文档是长期可复用的发布操作单。它只保存在私有源码仓库和 Obsidian，不部署到公开官网。

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
       ├─ xiaohongshu-qr.png
       ├─ vRemoter-latest.pkg
       ├─ vRemoter-1.0.0.pkg
       └─ 后续 DMG
```

上海服务器备案完成后，可只修改 DNS 指向，APP 内 URL 不需要改变。

### 当前上线状态（2026-08-28）

- `https://vremoter.vincentstudio.org/` 已在马来西亚服务器通过 Caddy 提供服务。
- `https://updates.vincentstudio.org/vremoter/`、`releases.json` 与 `commerce.json` 已通过公网 HTTPS 和 CORS 验证。
- TLS 证书由 Caddy 自动申请和续期；首次证书为 Let's Encrypt。
- 当前首发版只公开 `vRemoter-1.0.0.pkg`，页面没有 DMG；只有未来真正发布 APP-only 更新时才增加 DMG。
- 1.0.1 为 APP-only 更新：首次安装继续使用新版 PKG，已安装驱动的用户可使用 DMG。
- APP 与官网购买入口已暂停；远程配置中没有启用且有效的店铺时，APP 自动隐藏入口。
- 当前 PKG 尚未完成 Developer ID 签名与公证，下载页必须保留明确提示；完成签名、公证和实机验证后再替换同版本文件或发布新版本。
- Spaceship 的根域名 A 记录仍指向上海服务器；本次只新增了 `vremoter` 和 `updates`，两者指向 `47.250.150.45`。
- GitHub 草稿 PR：`VincentKingHsu/vRemoter#1`，分支为 `agent/private-self-hosted-release`。

## 2. 首次部署

1. 服务器安装 Caddy，并开放 TCP 80、443。
2. 上传 `docs/` 内容到 `/srv/vincentstudio/vremoter-site/`。
3. 上传 `Server/releases.json`、`docs/config/commerce.json` 与二维码到更新目录。
4. 安装 `Server/Caddyfile`，运行 `caddy validate` 后 reload。
5. 在 Spaceship 增加 `vremoter`、`updates` 两条 A 记录。
6. 验证 HTTPS、CORS、移动端页面和中国大陆访问。

## 3. 更换小红书链接

编辑公开更新目录中的 `commerce.json`：

- 修改 `stores[xiaohongshu].url`。
- 如二维码变化，替换 `xiaohongshu-qr.png` 并同步 `qrImageURL`。
- 更新 `updatedAt` 为当前 ISO 8601 时间。
- 用浏览器访问配置 URL，确认返回 JSON。
- 分别打开官网购买区和 APP 购买窗口验证。

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
  "name": "vRemoter-1.0.1.dmg",
  "browser_download_url": "https://updates.vincentstudio.org/vremoter/vRemoter-1.0.1.dmg",
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

- [ ] 三个遥控器 GitHub 仓库均为 Public。
- [ ] `../marketing/` 未进入 Git 暂存区。
- [ ] APP 更新地址和购买配置地址为 `updates.vincentstudio.org`。
- [ ] 自测和 Release 构建通过。
- [ ] APP、驱动、PKG/DMG 签名与公证通过。
- [ ] BlackHole 驱动许可路线已解决。
- [ ] 新机器 PKG 首装通过。
- [ ] 旧机器 DMG 覆盖升级通过。
- [ ] 自动更新按驱动标记选择正确安装包。
- [ ] 官网、小红书链接和二维码验证通过。
- [ ] Obsidian 项目档案已更新。
