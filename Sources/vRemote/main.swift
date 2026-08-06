// vRemote for macOS.
//
// 1. X6 voice key → matching Option toggle semantics
// 2. X6 ATVV + Mac microphone → aligned mix → vRemoteDr 2ch → Doubao
// 3. A physical Mac Option key controls the same X6 microphone session
//
// macOS-only. Requires:
//   * X6-Remote paired in System Settings → Bluetooth
//   * Accessibility permission (System Settings → Privacy & Security →
//     Accessibility) for Option observation and Search suppression
//   * vRemoteDriver.driver installed and visible as vRemoteDr 2ch in
//     System Settings → Sound → Input/Output
//   * Doubao IME configured for Option-as-voice-mode trigger
//
// Run:   swift run
// Quit:  menu bar icon → 退出, or Ctrl+C

import AppKit
import CoreGraphics
import Darwin
import Foundation

// MARK: - Virtual key codes

enum VK {
    static let option: CGKeyCode = 0x3A
    static let rightOption: CGKeyCode = 0x3D
}

// MARK: - Key synthesizer

enum Key {
    /// Lets the event tap distinguish Bridge-generated Option events from
    /// physical keyboards, other Bluetooth buttons, and external remappers.
    static let syntheticMarker: Int64 = 0x4D_49_52_42 // "MIRB"

    /// Walkie-talkie style: Option key down only (no matching up). Pair with `optionUp`.
    static func optionDown() {
        let src = CGEventSource(stateID: .hidSystemState)
        if let e = CGEvent(keyboardEventSource: src, virtualKey: VK.option, keyDown: true) {
            e.setIntegerValueField(
                .eventSourceUserData,
                value: syntheticMarker
            )
            e.post(tap: .cghidEventTap)
            print("[KEY] synthetic Option DOWN")
        }
    }
    static func optionUp() {
        let src = CGEventSource(stateID: .hidSystemState)
        if let e = CGEvent(keyboardEventSource: src, virtualKey: VK.option, keyDown: false) {
            e.setIntegerValueField(
                .eventSourceUserData,
                value: syntheticMarker
            )
            e.post(tap: .cghidEventTap)
            print("[KEY] synthetic Option UP")
        }
    }
    /// A deliberate short Option click for Doubao's toggle mode.
    ///
    /// Posting down and up back-to-back is sometimes too fast for an input
    /// method to classify as a real click, so keep the modifier down briefly.
    static func optionTap(completion: (() -> Void)? = nil) {
        optionDown()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.06) {
            optionUp()
            completion?()
        }
    }
}

// MARK: - Menu bar UI

final class AppController: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var statusItem: NSStatusItem!
    private var headerLabel: NSMenuItem!
    private var launchAtLoginItem: NSMenuItem!
    private var loggingToggleItem: NSMenuItem!
    private var logSizeItem: NSMenuItem!
    private var recordingToggleItem: NSMenuItem!
    private var recordingSizeItem: NSMenuItem!

    private var x6HIDConnected = false
    private var x6BLEConnected = false
    private var x6RemoteStreaming = false
    private var remoteStreaming = false

    private let x6 = X6HIDBridge()
    private let x6SearchSuppressor = X6SearchSuppressor()
    private let doubaoAudioState = DoubaoAudioStateMonitor()
    private lazy var x6Session = X6SessionCoordinator(
        doubaoState: doubaoAudioState
    )
    private let debugWindow = DebugWindowController()
    private let x6BLE = BLEBridge(
        nameHint: "X6-Remote",
        savedUUIDFilename: "x6-uuid.txt",
        recordingPrefix: "x6-voice",
        logTag: "X6-BLE",
        resetSessionOnConnect: true
    )

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        AppStorage.prepare()
        // Keep one continuous diagnostic history while X6 is being tuned.
        // Log.swift rotates at 5 MB; only the explicit menu action clears it.
        Log.setEnabled(true)
        print("[APP] ===== vRemoter 1.0 Beta V1 started =====")

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "⚠️"

        let menu = NSMenu()
        menu.delegate = self
        let header = NSMenuItem(title: "状态 · 启动中", action: nil, keyEquivalent: "")
        header.isEnabled = false
        menu.addItem(header)
        headerLabel = header

        let launch = NSMenuItem(
            title: "登录时自动启动",
            action: #selector(toggleLaunchAtLogin),
            keyEquivalent: ""
        )
        launch.target = self
        menu.addItem(launch)
        launchAtLoginItem = launch

        menu.addItem(.separator())
        menu.addItem(makeControlMenu())
        menu.addItem(makeLogMenu())
        menu.addItem(makeRecordingMenu())

        menu.addItem(.separator())
        let version = Bundle.main.object(
            forInfoDictionaryKey: "CFBundleShortVersionString"
        ) as? String ?? "未知"
        let versionItem = NSMenuItem(
            title: "版本 · \(version)",
            action: nil,
            keyEquivalent: ""
        )
        versionItem.isEnabled = false
        menu.addItem(versionItem)

        let quit = NSMenuItem(title: "退出", action: #selector(quit), keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)
        statusItem.menu = menu
        refreshMenuState()
        wireDebugWindow()

        // X6 HID observation and ATVV audio are independent connections.
        x6.onConnectionChanged = { [weak self] connected in
            self?.x6HIDConnected = connected
            self?.updateStatus()
        }
        // X6 does not emit a dependable HID edge on its first short press.
        // HID remains observation/search-suppression only; immediate voice
        // session control comes from AUDIO_START/AUDIO_STOP below.
        x6.onShortPress = { [weak self] in
            self?.x6Session.remoteHIDShortPress()
        }
        x6.onLongPressEnded = { [weak self] in
            self?.x6Session.remoteHIDLongPressEnded()
        }
        x6.onNativeSearchEdge = { [weak self] in
            self?.x6SearchSuppressor.arm()
        }
        x6SearchSuppressor.onOptionDownObserved = { [weak self] synthetic in
            self?.x6Session.optionDownObserved(isSynthetic: synthetic)
        }
        x6SearchSuppressor.onOptionUpObserved = { [weak self] synthetic in
            self?.x6Session.optionUpObserved(isSynthetic: synthetic)
        }
        x6BLE.onConnectionChanged = { [weak self] connected in
            self?.x6BLEConnected = connected
            if !connected { self?.x6RemoteStreaming = false }
            self?.refreshCombinedStreaming()
            self?.updateStatus()
        }
        x6BLE.onStreamingChanged = { [weak self] streaming, _ in
            self?.x6RemoteStreaming = streaming
            self?.refreshCombinedStreaming()
            self?.updateStatus()
        }
        x6BLE.onAudioStarted = { [weak self] reason, _ in
            self?.x6Session.remoteAudioStarted(reason: reason)
        }
        x6BLE.onAudioStopped = { [weak self] reason in
            self?.x6Session.remoteAudioStopped(reason: reason)
        }
        x6BLE.onLevel = { [weak self] db, _ in
            guard AudioPipe.shared.isRemoteInputEnabled else { return }
            self?.debugWindow.updateRemoteLevel(db)
        }
        x6Session.onMicrophoneCloseRequested = { [weak self] in
            self?.x6BLE.closeMicrophone(force: true)
        }
        x6Session.onMicrophoneOpenRequested = { [weak self] in
            guard AudioPipe.shared.isRemoteInputEnabled else {
                print("[AUDIO] X6 未勾选，跳过主动开麦")
                return
            }
            self?.x6BLE.openMicrophone()
        }
        x6Session.onStateChanged = { [weak self] status in
            self?.headerLabel.title = "状态 · \(status)"
            self?.updateStatus()
        }
        x6Session.start()
        x6SearchSuppressor.start()
        x6.start()
        x6BLE.start()

        // Start the loopback engine eagerly so device binding is verified
        // before the first BLE audio packet arrives.
        _ = AudioPipe.shared
        AudioPipe.shared.onMacLevel = { [weak self] db in
            self?.debugWindow.updateMacLevel(db)
        }
        AudioPipe.shared.onRouteChanged = { [weak self] _ in
            self?.updateStatus()
        }

        DispatchQueue.main.async { [weak self] in
            self?.debugWindow.show()
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        refreshMenuState()
    }

    private func makeLogMenu() -> NSMenuItem {
        let root = NSMenuItem(title: "日志", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "日志")

        let toggle = NSMenuItem(
            title: "记录日志",
            action: #selector(toggleLogging),
            keyEquivalent: ""
        )
        toggle.target = self
        submenu.addItem(toggle)
        loggingToggleItem = toggle

        let size = NSMenuItem(title: "占用 · 0 字节", action: nil, keyEquivalent: "")
        size.isEnabled = false
        submenu.addItem(size)
        logSizeItem = size

        let refresh = NSMenuItem(
            title: "刷新占用大小",
            action: #selector(refreshStorageSizes),
            keyEquivalent: ""
        )
        refresh.target = self
        submenu.addItem(refresh)

        let open = NSMenuItem(
            title: "打开日志文件夹",
            action: #selector(openLogFolder),
            keyEquivalent: ""
        )
        open.target = self
        submenu.addItem(open)

        let clear = NSMenuItem(
            title: "清空日志",
            action: #selector(clearLog),
            keyEquivalent: ""
        )
        clear.target = self
        submenu.addItem(clear)

        root.submenu = submenu
        return root
    }

    private func makeControlMenu() -> NSMenuItem {
        let root = NSMenuItem(title: "控制台", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "控制台")

        let open = NSMenuItem(
            title: "打开前台控制台",
            action: #selector(openDebugWindow),
            keyEquivalent: ""
        )
        open.target = self
        submenu.addItem(open)

        let stop = NSMenuItem(
            title: "关闭麦克风",
            action: #selector(stopMicrophone),
            keyEquivalent: ""
        )
        stop.target = self
        submenu.addItem(stop)

        let restart = NSMenuItem(
            title: "重启 App",
            action: #selector(restartApp),
            keyEquivalent: ""
        )
        restart.target = self
        submenu.addItem(restart)

        root.submenu = submenu
        return root
    }

    private func makeRecordingMenu() -> NSMenuItem {
        let root = NSMenuItem(title: "调试录音", action: nil, keyEquivalent: "")
        let submenu = NSMenu(title: "调试录音")

        let toggle = NSMenuItem(
            title: "保存 WAV 与原始数据",
            action: #selector(toggleRecording),
            keyEquivalent: ""
        )
        toggle.target = self
        submenu.addItem(toggle)
        recordingToggleItem = toggle

        let size = NSMenuItem(title: "占用 · 0 字节", action: nil, keyEquivalent: "")
        size.isEnabled = false
        submenu.addItem(size)
        recordingSizeItem = size

        let refresh = NSMenuItem(
            title: "刷新占用大小",
            action: #selector(refreshStorageSizes),
            keyEquivalent: ""
        )
        refresh.target = self
        submenu.addItem(refresh)

        let open = NSMenuItem(
            title: "打开录音文件夹",
            action: #selector(openRecordingFolder),
            keyEquivalent: ""
        )
        open.target = self
        submenu.addItem(open)

        let clear = NSMenuItem(
            title: "清空录音文件",
            action: #selector(clearRecordings),
            keyEquivalent: ""
        )
        clear.target = self
        submenu.addItem(clear)

        root.submenu = submenu
        return root
    }

    private func updateStatus() {
        let anyHID = x6HIDConnected
        let anyBLE = x6BLEConnected
        let doubaoSnapshot = doubaoAudioState.snapshotNow()
        let doubaoUsesVRemote = doubaoSnapshot.inputDeviceNames.contains("vRemoteDr 2ch")
        let statusText: String
        if doubaoSnapshot.isRecording && !doubaoUsesVRemote {
            statusText = "豆包输入设备错误"
            statusItem.button?.title = "⚠️"
        } else if remoteStreaming {
            statusText = "遥控器录音中"
            statusItem.button?.title = "🎙️"
        } else if anyHID && anyBLE {
            statusText = "已就绪"
            statusItem.button?.title = "🎤"
        } else if anyHID || anyBLE {
            statusText = "正在连接语音服务"
            statusItem.button?.title = "⏳"
        } else {
            statusText = "等待遥控器"
            statusItem.button?.title = "⚠️"
        }
        headerLabel.title = "状态 · \(statusText)"
        debugWindow.update(
            status: statusText,
            hidConnected: x6HIDConnected,
            bleConnected: x6BLEConnected,
            accessibilityAvailable: x6SearchSuppressor.isAvailable,
            remoteStreaming: remoteStreaming,
            macInputEnabled: AudioPipe.shared.isMacInputEnabled,
            remoteInputEnabled: AudioPipe.shared.isRemoteInputEnabled,
            doubaoIsRecording: doubaoSnapshot.isRecording,
            doubaoInput: doubaoSnapshot.deviceSummary,
            macLevelDB: nil,
            remoteLevelDB: nil
        )
    }

    private func wireDebugWindow() {
        debugWindow.onStopMicrophone = { [weak self] in
            self?.stopMicrophoneNow()
        }
        debugWindow.onRestartApp = { [weak self] in
            self?.restartAppNow()
        }
        debugWindow.onMacInputEnabledChanged = { [weak self] enabled in
            let audio = AudioPipe.shared
            audio.setInputEnabled(
                mac: enabled,
                remote: audio.isRemoteInputEnabled
            )
            self?.updateStatus()
        }
        debugWindow.onRemoteInputEnabledChanged = { [weak self] enabled in
            let audio = AudioPipe.shared
            audio.setInputEnabled(
                mac: audio.isMacInputEnabled,
                remote: enabled
            )
            if !enabled {
                self?.x6BLE.closeMicrophone(force: true)
                self?.debugWindow.updateRemoteLevel(-120)
            } else if self?.doubaoAudioState.snapshotNow().isRecording == true {
                self?.x6BLE.openMicrophone()
            }
            self?.updateStatus()
        }
        debugWindow.onOpenAccessibility = {
            if let url = URL(
                string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            ) {
                NSWorkspace.shared.open(url)
            }
        }
    }

    @objc private func openDebugWindow() {
        debugWindow.show()
    }

    @objc private func stopMicrophone() {
        stopMicrophoneNow()
    }

    private func stopMicrophoneNow() {
        x6Session.forceClose()
        x6BLE.closeMicrophone(force: true)
        AudioPipe.shared.setRemoteActive(false)
        updateStatus()
    }

    @objc private func restartApp() {
        restartAppNow()
    }

    private func restartAppNow() {
        stopMicrophoneNow()
        let bundleURL = Bundle.main.bundleURL
        // `NSWorkspace.openApplication` may reuse the current instance for an
        // accessory app. Use `/usr/bin/open -n` so macOS creates a genuinely
        // new process before this one exits.
        let launcher = Process()
        launcher.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        launcher.arguments = ["-n", bundleURL.path]
        do {
            try launcher.run()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                NSApp.terminate(nil)
            }
        } catch {
            print("[APP] 重启失败: \(error.localizedDescription)")
        }
    }

    private func refreshCombinedStreaming() {
        remoteStreaming = x6RemoteStreaming
    }

    private func refreshMenuState() {
        launchAtLoginItem?.state = LaunchAtLogin.isEnabled ? .on : .off
        loggingToggleItem?.state = Log.isEnabled ? .on : .off
        recordingToggleItem?.state = AppStorage.recordingEnabled ? .on : .off
        refreshSizeLabels()
    }

    private func refreshSizeLabels() {
        logSizeItem?.title = "占用 · \(AppStorage.formattedSize(Log.byteSize))"
        let recordingBytes = AppStorage.byteSize(
            of: AppStorage.recordingsDirectory
        )
        recordingSizeItem?.title =
            "占用 · \(AppStorage.formattedSize(recordingBytes))"
    }

    @objc private func toggleLaunchAtLogin() {
        do {
            try LaunchAtLogin.setEnabled(!LaunchAtLogin.isEnabled)
        } catch {
            headerLabel.title = "状态 · 登录启动设置失败"
        }
        refreshMenuState()
    }

    @objc private func toggleLogging() {
        Log.setEnabled(!Log.isEnabled)
        if Log.isEnabled {
            print("[APP] 日志已由用户开启")
        }
        refreshMenuState()
    }

    @objc private func toggleRecording() {
        let enabled = !AppStorage.recordingEnabled
        AppStorage.recordingEnabled = enabled
        x6BLE.setRecordingEnabled(enabled)
        refreshMenuState()
    }

    @objc private func refreshStorageSizes() {
        refreshSizeLabels()
    }

    @objc private func openLogFolder() {
        AppStorage.ensureDirectory(AppStorage.logsDirectory)
        NSWorkspace.shared.open(AppStorage.logsDirectory)
    }

    @objc private func openRecordingFolder() {
        AppStorage.ensureDirectory(AppStorage.recordingsDirectory)
        NSWorkspace.shared.open(AppStorage.recordingsDirectory)
    }

    @objc private func clearLog() {
        Log.clear()
        refreshSizeLabels()
    }

    @objc private func clearRecordings() {
        x6BLE.clearRecordings()
        refreshSizeLabels()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        x6.stop()
        x6SearchSuppressor.stop()
        x6Session.stop()
        x6BLE.stop()
        AudioPipe.shared.stop()
    }
}

// MARK: - Entry

let app = NSApplication.shared
let delegate = AppController()
app.delegate = delegate

// Convert SIGTERM (including `kill`/`pkill`) into a normal AppKit
// termination so Option and the CoreAudio IOProc are always released.
signal(SIGTERM, SIG_IGN)
let terminationSignal = DispatchSource.makeSignalSource(
    signal: SIGTERM,
    queue: .main
)
terminationSignal.setEventHandler {
    NSApp.terminate(nil)
}
terminationSignal.resume()

app.run()
