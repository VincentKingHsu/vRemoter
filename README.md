# vRemoter

把一只便宜但功能很野的 X6 Pro 蓝牙语音遥控器，变成 macOS 上可以给豆包输入法使用的随身语音输入器。

苹果遥控器动不动一百多，小米语音遥控器新的也常常五六十，而且基本还是“遥控器”。X6 Pro 这类小遥控器更有意思：正面有方向键、语音键和常用控制，背面有小键盘，里面还有飞鼠/陀螺仪。`vRemoter` 做的事情，就是把这类遥控器从“电视配件”改造成一个适合 Vibe Coding 的 Mac 语音外设。

当前版本：`1.0.0-beta.1`

## 亮点

- X6 Pro 遥控器语音键可以映射成 macOS 的 Option 键，用来唤起豆包输入法。
- X6 Pro 遥控器麦克风和 MacBook 内置麦克风可以同时送入同一个 CoreAudio 输入设备。
- 豆包输入法选择 `vRemoteDr 2ch` 后，可以吃到双麦克风混音后的声音。
- 遥控器开录、电脑 Option 关录，或者电脑 Option 开录、遥控器关录，都已经通过实机测试。
- 生成的是独立音频设备，不污染 BlackHole，也不覆盖旧版 Mi Remote Bridge。
- 状态栏应用提供日志、录音、麦克风开关和调试控制台，方便继续调硬件。

适合的场景很明确：你在房间里走来走去做语音编程，不想一直贴着电脑说话；又不想用蓝牙耳机那种经常吞掉开头几个字的链路。遥控器抓在手里，电脑麦克风在桌上，两路声音同时兜底，豆包负责最后的识别和润色。

## 当前实测状态

已通过：

- 豆包手动选择 `vRemoteDr 2ch` 后，双麦克风混音可用。
- 使用遥控器语音键开启录音，再用电脑 Option 关闭录音。
- 使用电脑 Option 开启录音，再用遥控器语音键关闭录音。
- 长按电脑 Option 开启录音。
- 短按遥控器语音键切换录音状态。

已知限制：

- X6 Pro 当前没有稳定上报“语音键长按松手”，所以遥控器物理长按还不能像电脑 Option 长按那样松手即关。
- 如果你愿意，也可以按着遥控器不放来“脑补长按”；它会录音，只是最后要记得再短按一下关闭。这个姿势不优雅，但确实有点赛博土法炼钢的味道。
- 当前第二路桌面麦克风固定为 MacBook 内置麦克风，后续版本会做成可选择外接麦克风。
- 双麦时间对齐目前使用第一轮实测值，复杂房间声场下可能还需要继续校准。

## 工作原理

`vRemoter` 分成两部分：

- 状态栏应用 `vRemote.app`：连接 X6 Pro，接收遥控器语音数据，处理按键映射，采集 MacBook 内置麦克风。
- 音频驱动 `vRemoteDriver.driver`：在系统里注册一个名为 `vRemoteDr 2ch` 的 CoreAudio 输入设备，让豆包把它当成可用麦克风。

音频路径：

```text
X6 Pro 遥控器麦克风（BLE / ATVV / ADPCM）──┐
                                           ├─ 对齐 + 等权混音 ─→ vRemoteDr 2ch ─→ 豆包输入法
MacBook 内置麦克风（CoreAudio）─────────────┘
```

两路输入没有主次之分。两边都有声音时做等权混音；只有一路有声音时，保留该路完整音量输出。这样近处、远处、转身、离桌走动时都有更高的容错。

## 安装前准备

你需要：

- macOS 12 或更高版本。
- 一只已经能和 Mac 蓝牙配对的 X6 Pro 语音遥控器。
- 本机已安装 BlackHole 2ch。构建脚本会复制它生成独立驱动，不会修改原 BlackHole。
- Swift / Xcode Command Line Tools。
- 管理员权限，用于安装 HAL 音频驱动。

首次启动应用时，macOS 可能会要求授予这些权限：

- 蓝牙：连接 X6 Pro。
- 麦克风：采集 MacBook 内置麦克风。
- 辅助功能：发送 Option 键给豆包。
- 输入监控：拦截 X6 Pro 原本可能触发的搜索键行为。

## 构建和安装

在项目根目录执行：

```bash
./Driver/build-driver.sh
sudo ./Driver/install-driver.sh
./run-self-tests.sh
./package-app.sh
./install-app.sh
open ~/Applications/vRemote.app
```

安装成功后，系统声音输入设备里应该能看到：

```text
vRemoteDr 2ch
```

如果看不到，可以重启一次 `coreaudiod` 或重启 Mac。

## 豆包设置

推荐设置：

1. 打开豆包输入法设置。
2. 进入语音输入的麦克风选择。
3. 手动选择 `vRemoteDr 2ch`。

如果豆包选择“自动检测”，它通常会跟随 macOS 当前系统输入设备。也就是说，如果系统输入还停在旧的 `MiRemoteV 2ch`，豆包自动检测就可能继续使用旧驱动，而不是 `vRemoteDr 2ch`。要用自动检测，请先在 macOS 系统声音设置里把输入设备切到 `vRemoteDr 2ch`。

## 使用方法

启动 `vRemote.app` 后，在菜单栏会出现状态图标。

常用操作：

- 短按 X6 Pro 语音键：打开豆包录音；再短按一次：结束录音。
- 按电脑 Option：也可以打开或关闭豆包录音。
- 用遥控器打开后，可以用电脑 Option 关闭。
- 用电脑 Option 打开后，可以用遥控器关闭。
- 在 vRemote 控制台里可以看到 MacBook 麦克风和 X6 麦克风的实时电平。

如果豆包没有出字，优先检查三件事：

- 豆包麦克风是否选择了 `vRemoteDr 2ch`。
- vRemote 控制台里 X6 和 MacBook 的麦克风电平是否在跳。
- 菜单栏里是否已经授予蓝牙、辅助功能、输入监控和麦克风权限。

## 数据位置

- X6 UUID：`~/Library/Application Support/vRemote/x6-uuid.txt`
- 日志：`~/Library/Logs/vRemote/vRemote.log`
- 调试录音：`~/Library/Application Support/vRemote/Recordings/`
- 应用：`~/Applications/vRemote.app`
- 驱动：`/Library/Audio/Plug-Ins/HAL/vRemoteDriver.driver`

日志默认开启，单文件最多 5 MB，会自动轮转。调试录音默认关闭；只有在菜单里主动打开录音功能时才会保存音频文件。

## 目录结构

- `Sources/vRemote/`：X6 HID、BLE/ATVV、豆包状态监听、按键映射和双麦混音。
- `SelfTests/`：ATVV/ADPCM 状态回归测试。
- `Driver/`：生成并安装独立 vRemote Driver 的脚本。
- `Packaging/`：macOS App 元数据。

## 许可

应用代码采用 MIT License。

`vRemoteDriver.driver` 基于 BlackHole 0.4.1 生成，遵循 GNU GPL v3。详见 `THIRD_PARTY_NOTICES.md`。
