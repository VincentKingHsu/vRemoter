(async () => {
  const C = {
    canvas: { r: 0.925, g: 0.929, b: 0.937 },
    panel: { r: 0.055, g: 0.059, b: 0.067 },
    surface: { r: 0.083, g: 0.091, b: 0.103 },
    surface2: { r: 0.102, g: 0.112, b: 0.124 },
    line: { r: 0.22, g: 0.23, b: 0.25 },
    lineSoft: { r: 0.15, g: 0.16, b: 0.18 },
    text: { r: 0.93, g: 0.94, b: 0.95 },
    secondary: { r: 0.55, g: 0.57, b: 0.61 },
    tertiary: { r: 0.39, g: 0.41, b: 0.45 },
    green: { r: 0.31, g: 0.82, b: 0.53 },
    greenDeep: { r: 0.06, g: 0.25, b: 0.16 },
    amber: { r: 0.96, g: 0.61, b: 0.19 },
    amberDeep: { r: 0.16, g: 0.13, b: 0.09 },
    red: { r: 0.94, g: 0.33, b: 0.34 },
    redDeep: { r: 0.25, g: 0.08, b: 0.09 },
    black: { r: 0.025, g: 0.028, b: 0.032 }
  };

  const paint = (color, opacity = 1) => [{ type: "SOLID", color, opacity }];
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Medium" });
  await figma.loadFontAsync({ family: "Inter", style: "Semi Bold" });

  function rect(parent, x, y, width, height, fill, radius = 0, stroke = null, strokeWeight = 1) {
    const node = figma.createRectangle();
    node.resize(width, height);
    node.x = x;
    node.y = y;
    node.fills = paint(fill);
    node.cornerRadius = radius;
    if (stroke) {
      node.strokes = paint(stroke);
      node.strokeWeight = strokeWeight;
    }
    parent.appendChild(node);
    return node;
  }

  function elevate(node, level = 1) {
    const alpha = level === 2 ? 0.42 : 0.28;
    const radius = level === 2 ? 20 : 10;
    const offsetY = level === 2 ? 10 : 5;
    node.effects = [
      {
        type: "DROP_SHADOW",
        color: { r: 0, g: 0, b: 0, a: alpha },
        offset: { x: 0, y: offsetY },
        radius,
        spread: 0,
        visible: true,
        blendMode: "NORMAL"
      },
      {
        type: "INNER_SHADOW",
        color: { r: 1, g: 1, b: 1, a: 0.055 },
        offset: { x: 0, y: 1 },
        radius: 0,
        spread: 0,
        visible: true,
        blendMode: "NORMAL"
      }
    ];
  }

  function label(parent, value, x, y, size, color = C.text, style = "Regular") {
    const node = figma.createText();
    node.fontName = { family: "Inter", style };
    node.fontSize = size;
    node.fills = paint(color);
    node.characters = value;
    node.x = x;
    node.y = y;
    parent.appendChild(node);
    return node;
  }

  function dot(parent, x, y, color, size = 8) {
    const node = figma.createEllipse();
    node.resize(size, size);
    node.x = x;
    node.y = y;
    node.fills = paint(color);
    parent.appendChild(node);
  }

  function statusPill(parent, x, y, width, textValue, tone) {
    const color = tone === "error" ? C.red : tone === "warn" ? C.amber : C.green;
    const bg = tone === "error" ? C.redDeep : tone === "warn" ? C.amberDeep : C.black;
    rect(parent, x, y, width, 28, bg, 14, tone === "idle" ? C.line : color);
    dot(parent, x + 14, y + 10, color, 8);
    label(parent, textValue, x + 31, y + 7, 11, tone === "idle" ? C.text : color, "Semi Bold");
  }

  function control(parent, x, y, width, textValue, active, type) {
    const activeColor = type === "solo" ? C.amber : C.red;
    const fill = active ? (type === "solo" ? C.amberDeep : C.redDeep) : C.black;
    const stroke = active ? activeColor : C.line;
    const button = rect(parent, x, y, width, 34, fill, 9, stroke);
    elevate(button, active ? 2 : 1);
    label(parent, textValue, x + 18, y + 9, 11, active ? activeColor : C.text, "Semi Bold");
  }

  function meter(parent, x, y, count, activeCount, activeColor, dimmed = false) {
    for (let i = 0; i < count; i += 1) {
      const active = !dimmed && i < activeCount;
      rect(parent, x + i * 14, y, 11, 17, active ? activeColor : C.black, 3);
    }
  }

  function micStrip(parent, x, y, width, title, subtitle, db, level, options) {
    const muted = !!options.muted;
    const solo = !!options.solo;
    const titleColor = muted ? C.tertiary : C.text;
    const backing = rect(parent, x + 1, y + 1, width - 2, 228, muted ? C.black : C.surface2, 12);
    if (solo) {
      backing.strokes = paint(C.amber);
      backing.strokeWeight = 1;
    }
    label(parent, title, x + 18, y + 18, 15, titleColor, "Semi Bold");
    label(parent, subtitle, x + 18, y + 42, 10, muted ? C.tertiary : C.secondary);
    dot(parent, x + 18, y + 66, muted ? C.tertiary : C.green, 8);
    label(parent, muted ? "因另一通道独奏而静音" : solo ? "正在独奏" : "有声音", x + 32, y + 64, 9, muted ? C.tertiary : solo ? C.amber : C.secondary, "Semi Bold");
    label(parent, db, x + width - 60, y + 64, 10, C.secondary, "Medium");
    meter(parent, x + 18, y + 88, 10, level, C.green, muted);
    label(parent, "低", x + 18, y + 111, 9, C.tertiary);
    label(parent, "高", x + 67, y + 111, 9, C.tertiary);
    control(parent, x + 18, y + 150, 62, "静音", muted, "mute");
    control(parent, x + 90, y + 150, 62, "独奏", solo, "solo");
    label(parent, muted ? "不参与混合" : solo ? "仅此路参与" : "参与混合", x + 18, y + 202, 9, muted ? C.tertiary : solo ? C.amber : C.secondary, "Medium");
    if (options.purchaseLink) label(parent, "购买遥控器 ↗", x + 102, y + 202, 8, C.green, "Medium");
  }

  function outputStrip(parent, x, y, width, state) {
    const outputError = state === "input_error" || state === "device_error";
    const outputCard = rect(parent, x + 1, y + 1, width - 2, 228, C.amberDeep, 12);
    elevate(outputCard, 1);
    rect(parent, x, y, width, 2, C.amber, 0);
    label(parent, "混合输出", x + 18, y + 18, 16, C.text, "Semi Bold");
    label(parent, "发送给豆包", x + 18, y + 42, 10, C.secondary);
    dot(parent, x + 18, y + 66, C.amber, 8);
    label(parent, state === "ending" ? "等待识别" : outputError ? "未输出" : "正在输出", x + 32, y + 64, 10, outputError ? C.red : C.amber, "Semi Bold");
    label(parent, state === "recording" ? "−7 dB" : outputError ? "−∞" : "−9 dB", x + width - 60, y + 64, 10, C.secondary, "Medium");
    meter(parent, x + 18, y + 88, 14, state === "recording" ? 10 : outputError ? 0 : 8, C.amber, outputError);
    label(parent, "低", x + 18, y + 111, 9, C.tertiary);
    label(parent, "高", x + 67, y + 111, 9, C.tertiary);
    rect(parent, x + 18, y + 143, width - 36, 48, C.surface, 11);
    dot(parent, x + 32, y + 162, C.amber, 8);
    label(parent, "两路已合并", x + 48, y + 157, 11, C.amber, "Semi Bold");
    label(parent, "vRemoteDr 2ch", x + width - 120, y + 157, 10, C.text, "Medium");
    label(parent, outputError ? "等待音频链路恢复" : state === "ending" ? "等待文字上屏" : "豆包正在接收", x + 18, y + 206, 9, outputError ? C.red : C.secondary);
  }

  function settingRow(parent, y, title, value, tone = "good", action = null) {
    const color = tone === "error" ? C.red : tone === "warn" ? C.amber : C.green;
    if (tone !== "good") rect(parent, 28, y - 4, 564, 26, tone === "error" ? C.redDeep : C.amberDeep, 8);
    dot(parent, 38, y + 2, color, 7);
    label(parent, title, 53, y, 9, C.secondary, "Medium");
    label(parent, value, 177, y, 9, tone === "good" ? C.text : color, "Semi Bold");
    if (action) {
      rect(parent, 508, y - 4, 72, 23, tone === "error" ? C.redDeep : C.amberDeep, 11, color);
      label(parent, action, 527, y + 2, 9, color, "Semi Bold");
    }
  }

  function bottomStatus(parent, mode) {
    const panel = rect(parent, 16, 326, 588, 184, C.surface, 15, C.line);
    elevate(panel, 1);
    const badInput = mode === "input_error";
    const permissionError = mode === "permission_error";
    const deviceError = mode === "device_error";

    settingRow(parent, 340, "豆包输入设备", badInput ? "MacBook Air 麦克风" : mode === "recording" ? "vRemoteDr 2ch · 录音中" : mode === "ending" ? "vRemoteDr 2ch · 处理中" : "vRemoteDr 2ch", badInput ? "error" : mode === "ending" ? "warn" : "good", badInput ? "设置方法" : null);
    settingRow(parent, 368, "音频驱动", deviceError ? "未安装或需要修复" : "vRemoteDr 2ch 可用", deviceError ? "error" : "good", deviceError ? "安装修复" : null);
    settingRow(parent, 396, "X6 连接", deviceError ? "BLE 音频未连接" : "HID · BLE · 语音流已就绪", deviceError ? "error" : "good", deviceError ? "蓝牙设置" : null);
    settingRow(parent, 424, "麦克风权限", permissionError ? "未授权" : "已授权", permissionError ? "error" : "good", permissionError ? "去授权" : null);
    settingRow(parent, 452, "辅助功能权限", permissionError ? "语音键无法正确映射" : "已授权", permissionError ? "error" : "good", permissionError ? "去授权" : null);
    settingRow(parent, 480, "输入监控权限", permissionError ? "无法拦截 X6 原生搜索" : "已授权", permissionError ? "warn" : "good", permissionError ? "去授权" : null);

  }

  function makePanel(name, mode, x, y) {
    const frame = figma.createFrame();
    frame.name = `vRemoter — ${name}`;
    frame.resize(620, 526);
    frame.x = x;
    frame.y = y;
    frame.fills = paint(C.panel);
    frame.cornerRadius = 20;
    frame.strokes = paint(C.line);
    frame.strokeWeight = 1;
    frame.clipsContent = true;
    board.appendChild(frame);
    elevate(frame, 2);

    const headerCard = rect(frame, 16, 16, 588, 54, C.surface, 15, C.line);
    elevate(headerCard, 1);
    label(frame, "vRemoter", 32, 27, 19, C.text, "Semi Bold");
    label(frame, "双麦语音输入", 32, 50, 9, C.secondary);

    const hasError = mode === "input_error" || mode === "permission_error" || mode === "device_error";
    const topStatus = mode === "recording" ? ["录音中", "warn"] : mode === "ending" ? ["优化识别中", "warn"] : hasError ? ["需要处理", "error"] : ["正在运行", "idle"];
    if (mode === "recording") {
      statusPill(frame, 408, 29, 82, topStatus[0], topStatus[1]);
      const stopButton = rect(frame, 500, 29, 84, 28, C.redDeep, 14, C.red);
      elevate(stopButton, 1);
      label(frame, "结束录音", 517, 36, 10, C.red, "Semi Bold");
    } else {
      statusPill(frame, 458, 29, 126, topStatus[0], topStatus[1]);
    }

    const mixerCard = rect(frame, 16, 82, 588, 230, C.surface2, 15, C.line);
    elevate(mixerCard, 1);
    rect(frame, 196, 82, 1, 230, C.lineSoft, 0);
    rect(frame, 376, 82, 1, 230, C.lineSoft, 0);

    const macMuted = mode === "x6solo";
    const x6Muted = mode === "macsolo";
    micStrip(frame, 16, 82, 180, "MacBook 麦克风", "电脑内置", macMuted ? "−∞" : mode === "recording" ? "−11 dB" : "−14 dB", mode === "recording" ? 8 : 6, { muted: macMuted, solo: mode === "macsolo" });
    micStrip(frame, 197, 82, 179, "X6 遥控器麦克风", "X6 遥控器", x6Muted ? "−∞" : mode === "recording" ? "−16 dB" : "−21 dB", mode === "recording" ? 7 : 5, { muted: x6Muted, solo: mode === "x6solo", purchaseLink: true });
    outputStrip(frame, 377, 82, 227, mode);
    bottomStatus(frame, mode);
    return frame;
  }

  const page = figma.currentPage;
  const oldBoard = page.findOne(node => node.type === "FRAME" && node.name === "vRemoter · Studio Mixer States");
  if (oldBoard) oldBoard.remove();

  const board = figma.createFrame();
  board.name = "vRemoter · Studio Mixer States";
  board.resize(1320, 2400);
  board.fills = paint(C.canvas);
  board.cornerRadius = 28;
  const maxRight = page.children.reduce((max, node) => Math.max(max, node.x + node.width), 0);
  board.x = maxRight + 100;
  board.y = 80;
  page.appendChild(board);

  label(board, "vRemoter · Studio Mixer 状态", 40, 28, 24, { r: 0.08, g: 0.09, b: 0.11 }, "Semi Bold");
  label(board, "沿用已选中的 Compact Mixer，只展示必要状态变化", 40, 61, 11, { r: 0.38, g: 0.40, b: 0.44 });

  const states = [
    ["01 · 待机 · 双路参与", "idle", 40, 110],
    ["02 · X6 独奏 · MacBook 联动变暗", "x6solo", 680, 110],
    ["03 · MacBook 独奏 · X6 联动变暗", "macsolo", 40, 686],
    ["04 · 双麦录音中 · 显示结束录音", "recording", 680, 686],
    ["05 · 豆包优化识别", "ending", 40, 1262],
    ["06 · 豆包输入设备错误", "input_error", 680, 1262],
    ["07 · 权限未完成", "permission_error", 40, 1838],
    ["08 · 驱动或 X6 连接异常", "device_error", 680, 1838]
  ];

  for (const state of states) {
    label(board, state[0], state[2], state[3] - 23, 11, { r: 0.32, g: 0.34, b: 0.38 }, "Semi Bold");
    makePanel(state[0], state[1], state[2], state[3]);
  }

  figma.currentPage.selection = [board];
  figma.viewport.scrollAndZoomIntoView([board]);
  figma.closePlugin("Studio Mixer 状态页面已生成");
})();
