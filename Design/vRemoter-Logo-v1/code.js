(async () => {
  const C = {
    canvas: { r: 0.925, g: 0.929, b: 0.937 },
    panel: { r: 0.055, g: 0.059, b: 0.067 },
    surface: { r: 0.083, g: 0.091, b: 0.103 },
    surface2: { r: 0.102, g: 0.112, b: 0.124 },
    line: { r: 0.22, g: 0.23, b: 0.25 },
    lineSoft: { r: 0.15, g: 0.16, b: 0.18 },
    text: { r: 0.93, g: 0.94, b: 0.95 },
    ink: { r: 0.08, g: 0.09, b: 0.11 },
    secondary: { r: 0.55, g: 0.57, b: 0.61 },
    tertiary: { r: 0.39, g: 0.41, b: 0.45 },
    green: { r: 0.31, g: 0.82, b: 0.53 },
    greenDeep: { r: 0.06, g: 0.25, b: 0.16 },
    remoteBody: { r: 0.78, g: 0.82, b: 0.84 },
    amber: { r: 0.96, g: 0.61, b: 0.19 },
    amberDeep: { r: 0.16, g: 0.13, b: 0.09 },
    red: { r: 0.94, g: 0.33, b: 0.34 },
    black: { r: 0.025, g: 0.028, b: 0.032 },
    white: { r: 1, g: 1, b: 1 }
  };

  const paint = (color, opacity = 1) => [{ type: "SOLID", color, opacity }];

  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Medium" });
  await figma.loadFontAsync({ family: "Inter", style: "Semi Bold" });

  function rect(parent, x, y, width, height, fill, radius = 0, stroke = null, strokeWeight = 1, opacity = 1) {
    const node = figma.createRectangle();
    node.resize(width, height);
    node.x = x;
    node.y = y;
    node.fills = paint(fill, opacity);
    node.cornerRadius = radius;
    if (stroke) {
      node.strokes = paint(stroke);
      node.strokeWeight = strokeWeight;
    }
    parent.appendChild(node);
    return node;
  }

  function ellipse(parent, x, y, size, fill, stroke = null, opacity = 1) {
    const node = figma.createEllipse();
    node.resize(size, size);
    node.x = x;
    node.y = y;
    node.fills = paint(fill, opacity);
    if (stroke) {
      node.strokes = paint(stroke);
      node.strokeWeight = 1;
    }
    parent.appendChild(node);
    return node;
  }

  function label(parent, value, x, y, size, color = C.text, style = "Regular", opacity = 1) {
    const node = figma.createText();
    node.fontName = { family: "Inter", style };
    node.fontSize = size;
    node.fills = paint(color, opacity);
    node.characters = value;
    node.x = x;
    node.y = y;
    parent.appendChild(node);
    return node;
  }

  function elevate(node, level = 1) {
    node.effects = [
      {
        type: "DROP_SHADOW",
        color: { r: 0, g: 0, b: 0, a: level === 2 ? 0.42 : 0.24 },
        offset: { x: 0, y: level === 2 ? 12 : 6 },
        radius: level === 2 ? 28 : 14,
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

  function hex(color) {
    const to255 = (n) => Math.round(n * 255).toString(16).padStart(2, "0").toUpperCase();
    return `#${to255(color.r)}${to255(color.g)}${to255(color.b)}`;
  }

  function brandMarkSvg(options = {}) {
    const dark = options.dark !== false;
    const mono = !!options.mono;
    const detail = options.detail || "full";
    const bg = dark ? "#0E0F11" : "#FFFFFF";
    const signal = mono ? (dark ? "#F3F5F6" : "#101216") : "#4FD187";
    const remote = mono ? signal : (dark ? "#C7D1D6" : "#20252A");
    const remoteBorder = mono ? (dark ? "#0E0F11" : "#FFFFFF") : (dark ? "#7F8A92" : "#5A646C");
    const border = dark ? "#2A2D32" : "#D7DAE0";
    const control = dark ? "#0E0F11" : "#FFFFFF";
    const waves = detail === "micro"
      ? `
        <path d="M86 108Q110 100.8 134 108" stroke="${signal}" stroke-opacity="0.94" stroke-width="11" stroke-linecap="round"/>
        <path d="M72 92Q110 73.95 148 92" stroke="${signal}" stroke-opacity="0.46" stroke-width="11" stroke-linecap="round"/>
      `
      : detail === "compact" || detail === "medium"
        ? `
          <path d="M86 108Q110 100.8 134 108" stroke="${signal}" stroke-opacity="0.96" stroke-width="9" stroke-linecap="round"/>
          <path d="M72 92Q110 73.95 148 92" stroke="${signal}" stroke-opacity="0.62" stroke-width="9" stroke-linecap="round"/>
          <path d="M86 76Q110 68.8 134 76" stroke="${signal}" stroke-opacity="0.34" stroke-width="9" stroke-linecap="round"/>
        `
        : `
          <path d="M95 124Q110 121.19 125 124" stroke="${signal}" stroke-opacity="0.98" stroke-width="8" stroke-linecap="round"/>
          <path d="M86 108Q110 100.8 134 108" stroke="${signal}" stroke-opacity="0.80" stroke-width="8" stroke-linecap="round"/>
          <path d="M72 92Q110 73.95 148 92" stroke="${signal}" stroke-opacity="0.62" stroke-width="8" stroke-linecap="round"/>
          <path d="M86 76Q110 68.8 134 76" stroke="${signal}" stroke-opacity="0.44" stroke-width="8" stroke-linecap="round"/>
          <path d="M95 60Q110 57.19 125 60" stroke="${signal}" stroke-opacity="0.28" stroke-width="8" stroke-linecap="round"/>
        `;
    const remoteControls = detail === "full" || detail === "medium"
      ? `
        <circle cx="78.85" cy="134" r="5" fill="none" stroke="${control}" stroke-width="2"/>
        <rect x="91.47" y="143" width="5" height="15" rx="2.5" fill="${control}" transform="rotate(-42.5 93.97 150.5)"/>
        <circle cx="141.15" cy="134" r="5" fill="none" stroke="${control}" stroke-width="2"/>
        <rect x="123.53" y="143" width="5" height="15" rx="2.5" fill="${control}" transform="rotate(42.5 126.03 150.5)"/>
      `
      : "";
    return `
      <svg width="220" height="220" viewBox="0 0 220 220" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="1" y="1" width="218" height="218" rx="51" fill="${bg}" stroke="${border}" stroke-width="2"/>
        <g transform="translate(-19.8 -19.8) scale(1.18)">
          ${waves}
          <!-- Locked 85-degree V geometry: both remote bodies share the same bottom overlap. -->
          <!-- Right remote sits underneath; the left remote gets a fine outline to show the overlap. -->
          <path d="M146.65 128L110 168" stroke="${remote}" stroke-width="20" stroke-linecap="round"/>
          <path d="M73.35 128L110 168" stroke="${remoteBorder}" stroke-width="22" stroke-linecap="round"/>
          <path d="M73.35 128L110 168" stroke="${remote}" stroke-width="20" stroke-linecap="round"/>
          ${remoteControls}
        </g>
      </svg>
    `;
  }

  function svgNode(parent, svg, x, y, width, height, name) {
    const node = figma.createNodeFromSvg(svg);
    node.name = name;
    node.resize(width, height);
    node.x = x;
    node.y = y;
    parent.appendChild(node);
    return node;
  }

  function swatch(parent, x, y, name, color, value) {
    rect(parent, x, y, 58, 58, color, 14, C.line);
    label(parent, name, x + 74, y + 4, 12, C.text, "Semi Bold");
    label(parent, value, x + 74, y + 25, 11, C.secondary, "Medium");
  }

  function makeWordmark(parent, x, y, scale = 1, dark = true) {
    const mark = svgNode(parent, brandMarkSvg({ dark }), x, y, 88 * scale, 88 * scale, "vRemoter mark");
    label(parent, "Remoter", x + 106 * scale, y + 15 * scale, 40 * scale, dark ? C.text : C.ink, "Semi Bold");
    return mark;
  }

  function makeIconSet(parent, x, y) {
    const sizes = [
      ["128", 128],
      ["64", 64],
      ["32", 32],
      ["16", 16]
    ];
    let offset = 0;
    for (const item of sizes) {
      const cellWidth = item[1] === 128 ? 184 : 116;
      const card = rect(parent, x + offset, y, cellWidth, 190, C.surface, 14, C.line);
      const iconX = x + offset + (cellWidth - item[1]) / 2;
      const detail = item[1] <= 16 ? "micro" : item[1] <= 32 ? "compact" : item[1] <= 64 ? "medium" : "full";
      svgNode(parent, brandMarkSvg({ dark: true, detail }), iconX, y + 26, item[1], item[1], `${item[0]} px logo`);
      label(parent, `${item[0]} px`, x + offset + 18, y + 158, 11, C.secondary, "Medium");
      offset += cellWidth + 16;
    }
  }

  const page = figma.currentPage;
  const oldLogo = page.findOne((node) => node.type === "FRAME" && node.name === "vRemoter · Brand Logo System");
  if (oldLogo) oldLogo.remove();

  const uiBoard = page.findOne((node) => node.type === "FRAME" && node.name === "vRemoter · Studio Mixer States");
  const maxRight = page.children.reduce((max, node) => Math.max(max, node.x + node.width), 0);

  const board = figma.createFrame();
  board.name = "vRemoter · Brand Logo System";
  board.resize(1280, 800);
  board.fills = paint(C.canvas);
  board.cornerRadius = 28;
  board.x = uiBoard ? uiBoard.x + uiBoard.width + 100 : maxRight + 100;
  board.y = uiBoard ? uiBoard.y : 80;
  page.appendChild(board);

  label(board, "vRemoter · Logo", 40, 30, 25, C.ink, "Semi Bold");
  label(board, "双遥控器组成 V · 分层波纹形成立式麦克风与发射意象", 40, 66, 12, C.tertiary, "Medium");

  const hero = rect(board, 40, 118, 744, 346, C.panel, 18, C.line);
  elevate(hero, 2);
  makeWordmark(board, 96, 194, 1.45, true);
  label(board, "DUAL REMOTES · V · VOICE SIGNAL", 250, 340, 11, C.secondary, "Medium");
  rect(board, 258, 372, 174, 2, C.line, 0);
  ellipse(board, 258, 400, 8, C.green);
  label(board, "V · 双遥控器", 276, 395, 11, C.secondary, "Medium");
  ellipse(board, 390, 400, 8, C.green, null, 0.5);
  label(board, "Waves · 麦克风网罩", 408, 395, 11, C.secondary, "Medium");

  const lightCard = rect(board, 816, 118, 200, 346, C.white, 18, C.line);
  elevate(lightCard, 1);
  svgNode(board, brandMarkSvg({ dark: false }), 850, 166, 132, 132, "Light app icon");
  label(board, "Light", 850, 332, 13, C.ink, "Semi Bold");
  label(board, "文档 / 浅色背景", 850, 358, 11, C.tertiary, "Medium");

  const monoCard = rect(board, 1048, 118, 192, 346, C.black, 18, C.line);
  elevate(monoCard, 1);
  svgNode(board, brandMarkSvg({ dark: true, mono: true }), 1078, 166, 132, 132, "Mono app icon");
  label(board, "Mono", 1078, 332, 13, C.text, "Semi Bold");
  label(board, "菜单栏 / 单色", 1078, 358, 11, C.secondary, "Medium");

  label(board, "Small-size test", 40, 510, 14, C.ink, "Semi Bold");
  makeIconSet(board, 40, 542);

  const palette = rect(board, 690, 542, 550, 210, C.panel, 16, C.line);
  elevate(palette, 1);
  label(board, "Brand colors", 722, 570, 15, C.text, "Semi Bold");
  swatch(board, 722, 610, "Panel", C.panel, hex(C.panel));
  swatch(board, 972, 610, "Signal", C.green, hex(C.green));
  swatch(board, 722, 682, "Remote body", C.remoteBody, hex(C.remoteBody));

  figma.currentPage.selection = [board];
  figma.viewport.scrollAndZoomIntoView([board]);
  figma.closePlugin("vRemoter logo 已生成");
})();
