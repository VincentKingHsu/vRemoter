# vRemoter

> 本仓库保存 vRemoter 的源码、设计源稿、构建脚本与测试。普通用户请通过 `vincentstudio.org` 系列域名访问官网、下载与更新服务。

[官方网站](https://vremoter.vincentstudio.org/) · [下载最新版](https://updates.vincentstudio.org/vremoter/) · [v1.0.1 Release](https://github.com/VincentKingHsu/vRemoter/releases/tag/v1.0.1)

## 产品定位

vRemoter 把蓝牙语音遥控器变成 macOS 上的 Vibe Coding 控制器：遥控器语音键控制豆包输入法，遥控器麦克风与 MacBook 麦克风混合为同一个 CoreAudio 输入设备 `vRemoteDr 2ch`。

已接入的遥控器：

- X6-Remote（VID `0x1D5A` / PID `0xC081`）
- Google Chromecast Remote（VID `0x18D1` / PID `0x9450`）

Chromecast Remote 当前已实现语音键单击切换：第一次单击打开豆包语音，第二次单击关闭。YouTube、Netflix 与信源键暂未重映射。

当前版本：`1.0.1`

## 支持开发

vRemoter 免费提供。如果它帮你省下了一点时间，欢迎请我喝杯咖啡，补充一点开发和 Token 费用。谢谢支持 🙏

| 微信 / WeChat | 支付宝 / Alipay | PayPal |
|---|---|---|
| <img src="docs/assets/donate/wechat.JPG" alt="微信打赏二维码" width="220"> | <img src="docs/assets/donate/alipay.JPG" alt="支付宝打赏二维码" width="220"> | <img src="docs/assets/donate/paypal.JPG" alt="PayPal donation QR code" width="220"> |

## 仓库与公开服务边界

| 内容 | 位置 | 是否公开 |
|---|---|---|
| APP、驱动构建、测试与设计 | 本 GitHub 仓库 | 是 |
| 官网静态源文件 | `docs/` | 是，部署结果见官网 |
| 官网 | [vremoter.vincentstudio.org](https://vremoter.vincentstudio.org/) | 是 |
| 更新、PKG/DMG、购买配置 | [updates.vincentstudio.org/vremoter](https://updates.vincentstudio.org/vremoter/) | 是 |
| 原始宣传视频与市场素材 | 仓库外 `../marketing/` | 否，不上传 Git |

遥控器相关 GitHub 仓库：

- [VincentKingHsu/vRemoter](https://github.com/VincentKingHsu/vRemoter)
- [VincentKingHsu/x6-remote-voice-bridge](https://github.com/VincentKingHsu/x6-remote-voice-bridge)
- [VincentKingHsu/MiRemoteVoice](https://github.com/VincentKingHsu/MiRemoteVoice)

## 目录

- `Sources/vRemote/`：APP 主程序、BLE/ATVV、双麦混音、UI、更新与购买配置。
- `Driver/`：生成 `vRemoteDriver.driver` 的实验性构建脚本。
- `Packaging/`：APP 元数据、本地化与 PKG 安装脚本。
- `Resources/`：APP 内置权限向导、商业入口与支持开发图片。
- `SelfTests/`：硬件协议与更新配置回归数据。
- `Design/`：冻结 UI 和 Logo 的 Figma 本地插件源稿。
- `docs/`：公开官网静态源文件。
- `Server/`：马来西亚服务器配置与发布清单模板。
- `OPERATIONS.md`：从构建到上线和回滚的操作手册。

## 构建

```bash
./run-self-tests.sh
./package-app.sh
./build-pkg.sh
./build-dmg.sh
```

- `PKG`：首次安装或驱动发生变化时使用，包含 APP 与音频驱动。
- `DMG`：仅更新 APP，适合已经安装过驱动且本次驱动未变化的用户。

1.0.1 是首次 APP-only 更新：PKG 供首次安装，DMG 供已经安装过驱动的用户覆盖更新。当前发布包尚未完成 Developer ID 签名与公证，下载页必须明确标注这一状态；正式广泛分发前仍须完成签名、公证与真实机器安装验证。

## 更新策略

APP 从以下地址读取版本清单：

`https://updates.vincentstudio.org/vremoter/releases.json`

- 普通 APP 更新：清单中同时提供 DMG/PKG，APP 自动优先下载 DMG。
- 驱动更新：将 `driver_update_required` 设为 `true`，APP 强制下载 PKG。
- 首次安装：官网始终推荐 PKG。

购买链接从以下地址动态读取：

`https://updates.vincentstudio.org/vremoter/commerce.json`

修改公开配置即可控制购买入口，不需要重新发布 APP。没有启用且有效的购买链接时，APP 会隐藏“购买遥控器”按钮。

## 发布前阻断项

1. 当前驱动是对 BlackHole GPL v3 二进制的修改构建。公开分发前必须选择：提供驱动对应源码与构建材料，或取得适用于闭源分发的商业授权。
2. APP、驱动与 PKG/DMG 尚需 Developer ID 签名和 notarization。
3. 每次发布都要验证首次 PKG 安装、DMG 覆盖更新、自动检查更新、购买链接刷新和卸载/回滚。

## 相关文档

- [完整发布与服务器运维手册](OPERATIONS.md)
- [第三方许可说明](THIRD_PARTY_NOTICES.md)
- [音频驱动说明](Driver/README.md)
- [冻结 UI 说明](Design/vRemoter-UI-v1-Frozen/UI-FREEZE.md)
