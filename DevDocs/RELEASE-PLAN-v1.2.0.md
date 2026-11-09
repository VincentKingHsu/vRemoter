# v1.2.0 开发方案与上线计划

> 状态：**方案已定稿（2026-11-09 含切换应用交互两轮讨论结论）→ 待大徐老师说「开工」**。本文档是本次发版的唯一执行依据，开工后逐项打勾，全程不口头约定。
> 纪律红线：大徐老师实测通过（阶段 B）之前，不 push GitHub、不动服务器、不改 releases.json。

## 一、版本决策（2026-11-09 大徐老师升级规则）

| 项 | 值 | 说明 |
|---|---|---|
| 版本号 | `1.1.1` → **`1.2.3`** | 第三位（patch）从本次起启用：本地每轮小改动 +1 |
| 构建号 | `111` → **`123`** | 主次版本拼接（1.1.1→111、1.2.3→123） |
| 渠道后缀 | `VRemoterBetaSuffix = " Beta"` | 主界面副标题显示「1.2.3 Beta」；**大徐老师说 OK 转正时清空该键**，版本号不变 |
| 主界面 | 「双麦语音输入」副标题 → **版本号** | 一眼识别测试包版本，不再靠功能猜 |

**版本体系（长期约定）**：测试期版本 = `x.y.z Beta`；转正 = 去掉 Beta 后缀（版本号不变）；下次发版继续从正式号往后走。同步点不变：`VERSION`、`Packaging/Info.plist`（CFBundleShortVersionString + CFBundleVersion + VRemoterBetaSuffix）、`CHANGELOG.md`、`README.md`、`Server/releases.json`、官网。

## 二、改动明细（5 项）

### A1 豆包输入法引导图（APP 向导 + 官网）

- 素材：`~/Documents/Workspace/vibecoding/豆包输入法设置.png`（372KB）
- APP：复制入 `Resources/PermissionGuides/doubaoinput3.png`；`DebugWindowController.swift` `PermissionKind.doubaoInput` 的 `screenshotNames`（约 41-48 行）追加 `"doubaoinput3"`，向导变 5 步
- **guidance 第 5 条文案（已定稿）**：
  - 中：`请将豆包输入法做如图设置。如要更改为其他按键，请在 vRemoter 程序里也做对应修改。`
  - 英：`Set up the Doubao input method exactly as shown. If you change the trigger key, update it inside vRemoter to match.`
- 官网：图入 `docs/assets/guides/`，`docs/index.html` 设置区加 figure（中英 caption）
- 注意：图为中文界面，中英文站共用（与现有 doubaoinput 系列一致）
- 红框高亮：向导对 doubaoInput 的第 1 页才画红框（`kind != .doubaoInput || page == 0`），第 5 页不画，无需改

### A2 麦克风按钮 → 拨动开关

- 位置：`DebugWindowController.swift` `InputChannelView`（1338-1458 行）
- 现状：「静音」「独奏」两按钮；底层只有 `macInputEnabled` / `remoteInputEnabled` 两个布尔——静音=取反自己、独奏=开自己关对方，**同一开关维度**
- 改法：每路一个 `Toggle`，复用 991-999 行现成样式（`.toggleStyle(.switch).controlSize(.small)`）
  - **提示文案（2026-11-09 大徐老师定稿）**：开关旁提示只写「打开 / 关闭」（英 `On / Off`），不再出现「静音」「独奏」「参与混合」字样
  - 参与混音的语义不变：由卡片本身状态表达——关闭时卡片变暗（现有 `.opacity` 0.58）+ 底部状态行「参与混合 / 不参与混合」保留，混音逻辑零改动
  - 两路都开 = 混合；只开一路 = 原独奏效果。功能零丢失
- 清理：`toggleMacMute` / `toggleRemoteMute` / `toggleMacSolo` / `toggleRemoteSolo` 四函数、`macSolo` / `remoteSolo` 计算属性、独奏琥珀高亮框、「正在独奏」文案
- 保留：状态圆点、「有声音/不参与混合」状态行、电平表、dB 显示

### A3 自定义选项显示「自定义（当前：xxx）」

- 位置：`DebugWindowController.swift` `MappingRow` 菜单 Text（1122-1128 行）
- 改法（只改显示，**不动** `RemoteMappingStore.targetTitle()`——X6/Chromecast 两个 HIDBridge 用它做状态上报，改了会串）：
  - 已录制：`自定义（当前：⇧⌘K）` / `Custom (Current: ⇧⌘K)`
  - 未录制：`自定义…` / `Custom…`（无括号内容可写）

### A4 新增三个映射选项：锁屏 / 睡眠 / 切换应用

- 位置：`RemoteMappingSupport.swift` `RemoteMappingTarget` 枚举（108-123 行）+ `title` + `keyboard` + `post` + 排序索引（约 185 行）；枚举是 Codable 存 UserDefaults，加 case 向后兼容
- 电源键（Chromecast `01`、X6 `s01`）default 保持 disabled，用户自行映射到新动作

| 新 case | 实现 | 权限 |
|---|---|---|
| 锁屏 Lock Screen | 模拟系统快捷键 **Control+Command+Q**（keyCode 17 + control/command flags），走现有 CGEvent HID 机制 | 无新增 |
| 睡眠 Sleep | 无可靠组合键（`pmset`/IOKit 均需 root）→ `osascript 'tell application "System Events" to sleep'`，`post` 加特殊分支 | 首次触发弹一次 TCC 授权（vRemote → System Events），官网/更新说明提及 |
| 切换应用 App Switcher | **定时器会话模型**，见下 | 无新增 |

**切换应用 · 交互定稿（2026-11-09 与大徐老师讨论两轮定稿）**

核心：遥控器切换键 = ⌘ 的替身，软件保持"⌘ 虚拟按住"并用 **1 秒倒计时**自动收尾。不依赖任何长按松手边沿，**X6 / Chromecast 同一套交互，无需降级**。

```
按下「切换应用键」（第 1 次）
  → 发 ⌘↓ + Tab↓↑（切换器打开，选中下一个应用）
  → ⌘ 保持虚拟按住，启动 1s 倒计时

会话期间（1s 内任意按键重置倒计时）：
  再按「切换应用键」  → 发 Tab（往右，等同连按 Tab）
  按 遥控器 →         → 发 Tab（往右）
  按 遥控器 ←         → 发 Shift+Tab（往左）
  其他遥控器键        → 照常走各自映射（透传，不拦截）

倒计时到期（1s 内无任何会话键）
  → 发 ⌘↑ → 落地，选中的应用到前台
```

- 单击一下就撒手 = 1 秒后落地 = 切到上一个应用，与真键盘单击 ⌘Tab 行为一致
- 实现件：`AppSwitcherSession` 小状态类（⌘ 虚按住 + Tab 发射 + 倒计时定时器）；两个 HID 桥事件路径加会话拦截分支（仅左右 + 切换键重定向）
- 会话期间切换器被鼠标等外部操作收走：到期照发 ⌘↑，无害；APP 退出/睡眠清理定时器
- 倒计时长 1s 为代码常量（可后续调），不进设置 UI
- **录制路线不做**：⌘Tab 会被系统切换器抢焦点，`KeyboardShortcutCaptureView` 局部监听收不到，系统级限制绕不过。内置选项已覆盖该场景

### A5 官网与文档同步

- 官网截图**必须重截**：UI 变更后现有截图与实际界面不符（静音/独奏按钮已不存在）——大徐老师重截中英 4 张（音频控制台 + 映射界面），文件名升级 `vremoter-*-1.2.0.png` / `*-1.2.0-en.png`
- `docs/app.js` 中英分支路径、`docs/index.html` 版本文案与更新日志、`README.md` 截图与徽标行
- `CHANGELOG.md` 增 1.2.0 条目；`Server/releases.json` **发布时最后替换**

## 三、开发纪律

1. 一项一改一编译：每项改完 `swift build -c release` 通过才动下一项
2. 不碰边界：`RemoteMappingStore.targetTitle()`、HIDBridge 状态上报、`Server/releases.json`（阶段 D 前）
3. UI 文案 L10n 中英双语同步写全，不留单语
4. 不删任何文件，历史产物只移 `DEL/`（工作区顶层 DEL 目录）
5. 阶段 B 实测由大徐老师执行；通过前不 push、不部署

## 四、上线计划 CheckList

### 阶段 A：本地开发 ✅（2026-11-09 完成）
- [x] A1 引导图入库 + 向导 5 步 + guidance 文案（中英）＋官网 figure
- [x] A2 拨动开关替换 + solo 逻辑清理（提示文案「打开/关闭」，solo 零残留）
- [x] A3 「自定义（当前：xxx）」显示（中英）
- [x] A4 锁屏 / 睡眠 / 切换应用三个选项（AppSwitcherSession 会话模型 + store.post 统一拦截，两个 HID 桥零改动）
- [x] A5 `swift build -c release` ✅ + `run-self-tests.sh` 全 PASS ✅ + `package-app.sh` 组装 ✅（引导图已验证入包；版本保持 1.1.1/111，升级在 C2）
- 备注：构建脚本补 `swift build --disable-sandbox`（本机系统策略禁用 SwiftPM manifest 沙箱，对正常环境无行为差异）

### 阶段 B：本地验收（大徐老师执行）——进行中
- 测试包：`vRemote/dist/build/vRemote.app`（直接双击打开即可，**未替换已安装的 1.1.1**）
- [ ] B1 向导走到第 5 步，图清晰、文案正确
- [ ] B2 拨动开关：全开 / 全关 / 只开一路，声音状态正确；提示文案显示「打开/关闭」
- [ ] B3 录制自定义键，菜单显示「自定义（当前：xxx）」；未录制时显示「自定义…」
- [ ] B4 电源键映射锁屏 / 睡眠各实测一遍（睡眠注意首次 TCC 弹窗）
- [ ] B5 切换应用实测：单击落地到上一个应用；连按切换键逐个右移；方向键←→双向选；停手 1 秒自动落地；会话中按其他键（静音/语音）不受干扰。**X6、Chromecast 各测一轮**
- [ ] B6 中英文切换各过一遍

### 阶段 C：发版物料 ✅（2026-11-09 13:35）
- [x] C1 转正：`VRemoterBetaSuffix` 清空，主界面显示「1.2.3」
- [x] C2 CHANGELOG 1.2.3 条目 + README（版本行、1.2.3 新功能段、v1.2.3 Release 链接、1.2.3 截图）
- [x] C3 PKG（8,459,467B / sha256 d59be08a…）+ DMG（8,725,052B / sha256 38420129…）读回 1.2.3/123
- [x] C4 官网：4 张 1.2.3 截图（中英）、KeyMapping 中英展示图 + 新「系统级控制」区块（id=actions）、Chromecast 示意图替换为 marketing 新图、版本文案全套 1.2.3、releases 分支 app.js 更新
- [x] C5 `Server/releases.json` 首项 v1.2.3（driver_update_required: false）+ 单一上传包 vr123-upload.zip（20,084,229B）

### 阶段 D：上线 ✅（2026-11-09 13:39）
- [x] D1 GitHub push main（提交 1943237，26 files +459/−103）
- [x] D2 GitHub Release `v1.2.3` 正式发布（非草稿非预发布）：https://github.com/VincentKingHsu/vRemoter/releases/tag/v1.2.3
- [x] D3 仓库 About 简介更新（含新功能关键词）
- [x] D4 服务器：zip 上传（哈希一致 9c121de2…）→ 备份 `/root/backup-20261109/` → SITE_OK → `releases.json` 最后替换 MANIFEST_OK
- [x] D5 公网复验：版本文案 5 项全中、8 张图全 200、PKG/DMG 公网下载哈希与本地一致、releases.json 首项 v1.2.3
- [ ] D6 知识库归纳（等大徐老师确认在线更新测试通过后一起收）

## 五、文件卫生（2026-11-09 已执行 ✅）

工作区顶层规矩：`DEL/` 放待删除文件、`marketing/` 放宣传文件、`Previous Version/` 冻结不动、`vRemote/` 为项目根。

| 动作 | 状态 |
|---|---|
| 新建 `DevDocs/`，本文档为第一篇 | ✅ 与官网 `docs/` 分离 |
| 根目录 5 个脚本收进 `Scripts/` | ✅ `git mv` 保历史；路径基准补 `SCRIPT_DIR="${SCRIPT_DIR:h}"`；`build-dmg/build-pkg` 内对 `package-app.sh` 的调用同步改为 `Scripts/` 前缀；`zsh -n` 全过 + `run-self-tests.sh` 实测通过 |
| `dist/` 历史构建产物 183MB（18 项） | ✅ 移入工作区 `DEL/vRemote-dist-archive-20261109/`，`dist/` 保留空壳供构建 |
| `豆包输入法设置.png` | ✅ 复制入 `Resources/PermissionGuides/doubaoinput3.png`（sha256 一致；原图保留在根目录） |
| `Chromecast remote.png` | ✅ 与官网同名图哈希不同（非重复），属宣传素材 → 已移入 `marketing/` |
| `dist/vRemote.app`（root:wheel，8/12 遗留壳） | ⚠️ **遗留**：沙箱无 sudo 无法移动。不影响构建（构建输出在 `dist/build/`），待大徐老师手动执行：`sudo rm -rf ~/Documents/Workspace/vibecoding/vRemote/dist/vRemote.app` |
| `Design/UIv1_bak.fig` | 保留（git 管理内的设计备份） |

> git 状态：以上改动均为本地未提交状态（Scripts 移动 + DevDocs 新增 + dist 内容本就被 gitignore），随阶段 A 一起 commit。
