import CoreAudio

// MARK: - CoreAudio process-object API compatibility
//
// `kAudioHardwarePropertyProcessObjectList`,
// `kAudioHardwarePropertyTranslatePIDToProcessObject`,
// `kAudioProcessPropertyIsRunningInput` and `kAudioProcessPropertyDevices`
// were introduced with the macOS 14.2 SDK. The macOS 13.1 SDK on this machine
// does not declare them, so they are re-declared here under distinct names.
//
// The values are not guesses: they were read back from the constant pool of
// the official arm64 vRemoter 1.1.1 binary (built against the macOS 14.4 SDK),
// where each selector sits next to its scope as a little-endian pair:
//
//   'prs#' + 'glob'   process object list
//   'piri' + 'glob'   process is running input
//   'pdv#' + 'inpt'   process input devices
//   'id2p' + 'glob'   translate PID to process object
//
// Behaviour on systems older than macOS 14.2 is unchanged: CoreAudio reports
// an unknown property and the monitor already degrades to `.unavailable`.

enum CoreAudioProcessCompat {
    static let processObjectList: AudioObjectPropertySelector = 0x70727323  // 'prs#'
    static let translatePIDToProcessObject: AudioObjectPropertySelector = 0x69643270  // 'id2p'
    static let isRunningInput: AudioObjectPropertySelector = 0x70697269  // 'piri'
    static let devices: AudioObjectPropertySelector = 0x70647623  // 'pdv#'
}
