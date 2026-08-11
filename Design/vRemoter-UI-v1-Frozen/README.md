# vRemoter Figma 状态页面

这是一个本地 Figma 插件包。它不会修改 vRemote 工程代码，也不会把文件散到工程根目录。

## 使用方法

1. 打开 Figma 桌面版，新建一个 Design 文件，或打开你准备放置页面的文件。
2. 打开菜单：`Plugins → Development → Import new plugin from manifest…`
3. 选择本文件夹里的 `manifest.json`。
4. 再次打开：`Plugins → Development → vRemoter UI States`。
5. 插件会在当前页面右侧生成一张 `vRemoter · Studio Mixer States`，里面有 8 个代表状态页面。

## 这 8 个页面

- 待机：MacBook 与 X6 都参与混合
- X6 独奏：X6 工作，MacBook 联动变暗
- MacBook 独奏：MacBook 工作，X6 联动变暗
- 双麦录音中：显示条件式“结束录音”按钮
- 豆包优化识别中
- 豆包输入设备错误：显示“设置方法”
- 麦克风、辅助功能、输入监控权限未完成：分别显示“去授权”
- 驱动或 X6 连接异常：显示“安装修复”与“蓝牙设置”

这一版严格沿用原来已选中的 `vRemote Compact Mixer`：深色面板、同一调音台里的 MacBook / X6 / 混合输出三路、右侧混合输出用琥珀色提高层级、底部使用一块紧凑的真实状态区。前两路使用“静音 / 独奏”；静音点亮为红色，独奏点亮为琥珀色，同时让另一支麦克风联动变暗。混合输出的“两路已合并”只是状态，不是按钮。

底部设置检查区完整覆盖：豆包输入设备、vRemoteDr 2ch 驱动、X6 的 HID / BLE / 语音流、麦克风权限、辅助功能权限和输入监控权限。蓝牙权限合并进 X6 状态；Option 映射只有在相关权限异常时才显示具体原因，不单独凑一条正常状态。登录时自动启动和调试工具属于低频设置，保留在菜单栏，不占主面板。

产品与 GitHub 仓库统一使用 `vRemoter`；`vRemoteDr 2ch` 继续作为系统中的音频设备名称。X6 通道显示为“X6 遥控器麦克风”，并预留一个小型“购买遥控器”链接位置。

## 重新生成

如果需要重新生成，直接再次运行插件即可。它只会删除当前页面中同名的 `vRemoter · Studio Mixer States`，不会碰其他图层，也不会删除原来的 `Selected - vRemote Compact Mixer`。
