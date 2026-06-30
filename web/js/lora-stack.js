import { app } from "/scripts/app.js";

const NODE_NAME = "CharlierzPowerLoraStack";
const SHOW_STRENGTHS = "Show Strengths";
const SINGLE = "Single Strength";
const SEPARATE = "Separate Model & Clip";
const ROW_HEIGHT = 24;

app.registerExtension({
  name: "charlierz.power_lora_stack",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    nodeType["@Show Strengths"] = { type: "combo", values: [SINGLE, SEPARATE] };

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);
      initializeLoraStackNode(this);
      if (!getLoraWidgets(this).length) addStaticWidgets(this);
      resizeToFit(this);
    };

    const originalConfigure = nodeType.prototype.configure;
    nodeType.prototype.configure = function (info) {
      const loraValues = (info?.widgets_values || []).filter(
        (value) => value && typeof value === "object" && "lora" in value,
      );
      originalConfigure?.apply(this, arguments);
      initializeLoraStackNode(this);
      clearLoraStackWidgets(this);
      for (const value of loraValues) addLoraWidget(this, value);
      addStaticWidgets(this);
      resizeToFit(this);
    };

    nodeType.prototype.getExtraMenuOptions = function (_, options) {
      options.push({
        content: "Toggle all LoRAs",
        callback: () => {
          const allOn = getLoraWidgets(this).every((widget) => widget.value?.on);
          for (const widget of getLoraWidgets(this)) widget.value.on = !allOn;
          this.setDirtyCanvas(true, true);
        },
      });
    };

    const originalGetSlotInPosition = nodeType.prototype.getSlotInPosition;
    nodeType.prototype.getSlotInPosition = function (canvasX, canvasY) {
      const slot = originalGetSlotInPosition?.apply(this, arguments);
      if (slot) return slot;
      const widget = getLoraWidgetAtCanvasY(this, canvasY);
      return widget ? { widget, output: { type: "LORA WIDGET" } } : undefined;
    };

    const originalGetSlotMenuOptions = nodeType.prototype.getSlotMenuOptions;
    nodeType.prototype.getSlotMenuOptions = function (slot) {
      if (slot?.widget?.name?.startsWith("lora_")) {
        return getRowMenuItems(this, slot.widget);
      }
      return originalGetSlotMenuOptions?.apply(this, arguments);
    };
  },
});

function initializeLoraStackNode(node) {
  node.serialize_widgets = true;
  node.properties ??= {};
  node.properties[SHOW_STRENGTHS] ??= SINGLE;
  node._charlierzLoraCounter ??= 0;
}

function clearLoraStackWidgets(node) {
  node.widgets = (node.widgets || []).filter(
    (widget) => !widget.name?.startsWith("lora_") && !widget.name?.startsWith("charlierz_lora_"),
  );
}

function addStaticWidgets(node) {
  node.widgets = (node.widgets || []).filter((widget) => !widget.name?.startsWith("charlierz_lora_"));
  const topSpacer = makeSpacerWidget("charlierz_lora_top_spacer", 4);
  const addSpacer = makeSpacerWidget("charlierz_lora_add_spacer", 4);
  const addButton = makeButtonWidget("charlierz_lora_add", "➕ Add Lora", async (event) => {
    await chooseLora(event, (lora) => {
      if (!lora) return;
      addLoraWidget(node, { on: true, lora, strength: 1, strengthTwo: null });
      addStaticWidgets(node);
      resizeToFit(node);
      node.setDirtyCanvas(true, true);
    });
  });
  node.addCustomWidget(topSpacer);
  node.addCustomWidget(makeHeaderWidget());
  node.addCustomWidget(addSpacer);
  node.addCustomWidget(addButton);
  orderWidgets(node);
}

function orderWidgets(node) {
  const widgets = node.widgets || [];
  const topSpacer = widgets.find((widget) => widget.name === "charlierz_lora_top_spacer");
  const header = widgets.find((widget) => widget.name === "charlierz_lora_header");
  const addSpacer = widgets.find((widget) => widget.name === "charlierz_lora_add_spacer");
  const add = widgets.find((widget) => widget.name === "charlierz_lora_add");
  const loras = widgets.filter((widget) => widget.name?.startsWith("lora_"));
  const others = widgets.filter(
    (widget) => widget !== topSpacer && widget !== header && widget !== addSpacer && widget !== add && !widget.name?.startsWith("lora_"),
  );
  node.widgets = [
    ...others,
    ...(topSpacer ? [topSpacer] : []),
    ...(header ? [header] : []),
    ...loras,
    ...(addSpacer ? [addSpacer] : []),
    ...(add ? [add] : []),
  ];
}

function addLoraWidget(node, value) {
  initializeLoraStackNode(node);
  node._charlierzLoraCounter += 1;
  const widget = makeLoraWidget(`lora_${node._charlierzLoraCounter}`, value);
  node.addCustomWidget(widget);
  orderWidgets(node);
  return widget;
}

function getLoraWidgets(node) {
  return (node.widgets || []).filter((widget) => widget.name?.startsWith("lora_"));
}

function resizeToFit(node) {
  const computed = node.computeSize?.() || node.size || [320, 100];
  node.size = node.size || [320, 100];
  node.size[0] = Math.max(node.size[0], 360, computed[0]);
  node.size[1] = Math.max(computed[1], 60);
}

function makeSpacerWidget(name, height) {
  return {
    name,
    type: "custom",
    value: null,
    options: { serialize: false },
    draw() {},
    computeSize(width) {
      return [width, height];
    },
  };
}

function makeHeaderWidget() {
  return {
    name: "charlierz_lora_header",
    type: "custom",
    value: null,
    options: { serialize: false },
    draw(ctx, node, width, y, height) {
      const widgets = getLoraWidgets(node);
      this._areas = {};
      if (!widgets.length) return;
      const separate = node.properties?.[SHOW_STRENGTHS] === SEPARATE;
      const allOn = widgets.every((widget) => widget.value?.on);
      const allOff = widgets.every((widget) => widget.value?.on === false);
      const toggleValue = allOn ? true : allOff ? false : null;
      const margin = 10;
      const innerMargin = margin * 0.33;
      const midY = y + height / 2;
      let posX = margin;

      ctx.save();
      this._areas.toggle = boundsFromX(drawTogglePart(ctx, { posX, posY: y, height, value: toggleValue }), y, height);
      posX += this._areas.toggle[2] + innerMargin;
      ctx.globalAlpha = app.canvas.editor_alpha * 0.65;
      ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText("Toggle All", posX, midY);
      ctx.textAlign = "right";
      ctx.fillText(separate ? "Model / Clip" : "Strength", width - 14, midY);
      ctx.restore();
    },
    mouse(event, pos, node) {
      if (event.type !== "pointerdown" || !inArea(pos, this._areas?.toggle)) return false;
      const widgets = getLoraWidgets(node);
      const allOn = widgets.every((widget) => widget.value?.on);
      for (const widget of widgets) widget.value.on = !allOn;
      node.setDirtyCanvas(true, true);
      return true;
    },
  };
}

function makeButtonWidget(name, label, callback) {
  return {
    name,
    type: "custom",
    value: null,
    options: { serialize: false },
    draw(ctx, _node, width, y, height) {
      drawWidgetButton(ctx, { size: [width - 30, height], pos: [15, y] }, label, false);
    },
    mouse(event, _pos, node) {
      if (event.type === "pointerdown") {
        callback(event, node);
        return true;
      }
      return false;
    },
  };
}

function makeLoraWidget(name, initialValue) {
  const widget = {
    name,
    type: "custom",
    value: normalizeValue(initialValue),
    options: { serialize: true },
    serializeValue() {
      return this.value;
    },
    draw(ctx, node, width, y, height) {
      const separate = node.properties?.[SHOW_STRENGTHS] === SEPARATE;
      const value = normalizeValue(this.value);
      this.value = value;
      const margin = 10;
      const innerMargin = margin * 0.33;
      const lowQuality = isLowQuality();
      const midY = y + height / 2;
      let posX = margin;
      let rightX = width - margin - innerMargin - innerMargin;

      this._areas = {};

      ctx.save();
      drawRoundedRectangle(ctx, { pos: [posX, y], size: [width - margin * 2, height] });
      this._areas.toggle = boundsFromX(drawTogglePart(ctx, { posX, posY: y, height, value: value.on }), y, height);
      posX += this._areas.toggle[2] + innerMargin;

      if (lowQuality) {
        ctx.restore();
        return;
      }

      if (!value.on) ctx.globalAlpha = app.canvas.editor_alpha * 0.4;
      ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";

      const clipStrength = value.strengthTwo ?? value.strength;
      const [clipDown, clipText, clipUp] = drawNumberWidgetPart(ctx, {
        posX: rightX,
        posY: y,
        height,
        value: separate ? clipStrength : value.strength,
        direction: -1,
      });
      this._areas.modelDown = boundsFromX(clipDown, y, height);
      this._areas.modelValue = boundsFromX(clipText, y, height);
      this._areas.modelUp = boundsFromX(clipUp, y, height);
      rightX = clipDown[0] - innerMargin;

      if (separate) {
        this._areas.clipDown = this._areas.modelDown;
        this._areas.clipValue = this._areas.modelValue;
        this._areas.clipUp = this._areas.modelUp;

        rightX -= innerMargin;
        const [modelDown, modelText, modelUp] = drawNumberWidgetPart(ctx, {
          posX: rightX,
          posY: y,
          height,
          value: value.strength,
          direction: -1,
        });
        this._areas.modelDown = boundsFromX(modelDown, y, height);
        this._areas.modelValue = boundsFromX(modelText, y, height);
        this._areas.modelUp = boundsFromX(modelUp, y, height);
        rightX = modelDown[0] - innerMargin;
      }

      const loraW = Math.max(30, rightX - posX - innerMargin);
      this._areas.lora = [posX, y, loraW, height];
      ctx.fillText(fitString(ctx, value.lora || "<choose lora>", loraW), posX, midY);
      ctx.restore();
    },
    mouse(event, pos, node) {
      if (event.type === "contextmenu") {
        event.preventDefault?.();
        showRowMenu(event, node, this);
        return true;
      }
      if (event.type === "pointermove" && this._dragStrength) {
        const dx = pos[0] - this._dragStrength.startX;
        if (Math.abs(dx) >= 2) this._dragStrength.moved = true;
        const value = roundDisplay(this._dragStrength.startValue + dx * 0.01);
        this._dragStrength.setValue(value);
        node.setDirtyCanvas(true, true);
        return true;
      }
      if (event.type === "pointerup" && this._dragStrength) {
        const drag = this._dragStrength;
        this._dragStrength = null;
        if (!drag.moved) promptStrength(event, drag.getValue(), drag.setValue, node);
        return true;
      }
      if (event.type !== "pointerdown") return false;
      const areas = this._areas || {};
      if (event.button === 2) {
        event.preventDefault?.();
        showRowMenu(event, node, this);
        return true;
      }
      if (inArea(pos, areas.toggle)) {
        this.value.on = !this.value.on;
      } else if (inArea(pos, areas.lora)) {
        chooseLora(event, (lora) => {
          this.value.lora = lora;
          node.setDirtyCanvas(true, true);
        });
      } else if (inArea(pos, areas.modelDown)) {
        this.value.strength = roundStrengthStep(this.value.strength - 0.05);
      } else if (inArea(pos, areas.modelUp)) {
        this.value.strength = roundStrengthStep(this.value.strength + 0.05);
      } else if (inArea(pos, areas.modelValue)) {
        this._dragStrength = {
          startX: pos[0],
          startValue: this.value.strength,
          moved: false,
          getValue: () => this.value.strength,
          setValue: (value) => (this.value.strength = value),
        };
      } else if (inArea(pos, areas.clipDown)) {
        this.value.strengthTwo = roundStrengthStep((this.value.strengthTwo ?? this.value.strength) - 0.05);
      } else if (inArea(pos, areas.clipUp)) {
        this.value.strengthTwo = roundStrengthStep((this.value.strengthTwo ?? this.value.strength) + 0.05);
      } else if (inArea(pos, areas.clipValue)) {
        this._dragStrength = {
          startX: pos[0],
          startValue: this.value.strengthTwo ?? this.value.strength,
          moved: false,
          getValue: () => this.value.strengthTwo ?? this.value.strength,
          setValue: (value) => (this.value.strengthTwo = value),
        };
      } else {
        showRowMenu(event, node, this);
      }
      node.setDirtyCanvas(true, true);
      return true;
    },
  };
  return widget;
}

function normalizeValue(value) {
  if (!value || typeof value !== "object") return { on: true, lora: null, strength: 1, strengthTwo: null };
  return {
    on: value.on !== false,
    lora: value.lora ?? null,
    strength: Number(value.strength ?? 1),
    strengthTwo: value.strengthTwo == null ? null : Number(value.strengthTwo),
  };
}

function getLoraWidgetAtCanvasY(node, canvasY) {
  for (const widget of getLoraWidgets(node)) {
    if (widget.last_y == null) continue;
    const top = node.pos[1] + widget.last_y;
    const bottom = top + LiteGraph.NODE_WIDGET_HEIGHT;
    if (canvasY >= top && canvasY <= bottom) return widget;
  }
  return null;
}

function promptStrength(event, currentValue, onValue, node) {
  app.canvas.prompt("Strength", String(currentValue), (value) => {
    const parsed = Number.parseFloat(value);
    if (!Number.isNaN(parsed)) {
      onValue(parsed);
      node.setDirtyCanvas(true, true);
    }
  }, event);
}

function getRowMenuItems(node, widget) {
  const widgets = getLoraWidgets(node);
  const index = widgets.indexOf(widget);
  return [
    { content: "ℹ️ Show Info", disabled: !widget.value?.lora, callback: () => showLoraInfo(widget.value.lora) },
    null,
    { content: "Move to top", disabled: index <= 0, callback: () => moveWidgetTo(node, widget, 0) },
    { content: "Move up", disabled: index <= 0, callback: () => moveWidget(node, widget, -1) },
    { content: "Move down", disabled: index === widgets.length - 1, callback: () => moveWidget(node, widget, 1) },
    { content: "Move to bottom", disabled: index === widgets.length - 1, callback: () => moveWidgetTo(node, widget, widgets.length - 1) },
    { content: "Remove", callback: () => removeWidget(node, widget) },
  ];
}

function showRowMenu(event, node, widget) {
  new LiteGraph.ContextMenu(getRowMenuItems(node, widget), { event });
}

async function showLoraInfo(lora) {
  try {
    const { RgthreeLoraInfoDialog } = await import("/extensions/rgthree-comfy/dialog_info.js");
    const dialog = new RgthreeLoraInfoDialog(lora).show();
    dialog.addEventListener?.("close", () => {});
    return;
  } catch (error) {
    console.error("[comfyui-charlierz] rgthree LoRA info dialog is unavailable", error);
  }
  app.ui?.dialog?.show?.(`rgthree LoRA info dialog is unavailable for: ${lora}`);
}

function moveWidget(node, widget, delta) {
  const loras = getLoraWidgets(node);
  moveWidgetTo(node, widget, loras.indexOf(widget) + delta);
}

function moveWidgetTo(node, widget, loraIndex) {
  const widgets = node.widgets;
  const loras = getLoraWidgets(node);
  const target = loras[loraIndex];
  if (!target || target === widget) return;

  const from = widgets.indexOf(widget);
  const to = widgets.indexOf(target);
  widgets.splice(from, 1);
  widgets.splice(to, 0, widget);
  node.setDirtyCanvas(true, true);
}

function removeWidget(node, widget) {
  const index = node.widgets.indexOf(widget);
  if (index >= 0) node.widgets.splice(index, 1);
  resizeToFit(node);
  node.setDirtyCanvas(true, true);
}

async function chooseLora(event, onChoose) {
  try {
    const [{ showLoraChooser }, { rgthreeApi }] = await Promise.all([
      import("/extensions/rgthree-comfy/utils_menu.js"),
      import("/rgthree/common/rgthree_api.js"),
    ]);
    const details = await rgthreeApi.getLoras();
    showLoraChooser(event, (value) => value && value !== "NONE" && onChoose(value), null, details.map((lora) => lora.file));
    return;
  } catch (error) {
    console.warn("[comfyui-charlierz] Falling back to basic LoRA menu", error);
  }

  const loras = await getFallbackLoras();
  new LiteGraph.ContextMenu(
    loras.map((lora) => ({ content: lora, callback: () => onChoose(lora) })),
    {
      event,
      title: "Choose a lora",
      className: "dark",
      scale: Math.max(1, app.canvas.ds?.scale ?? 1),
    },
  );
}

async function getFallbackLoras() {
  const response = await fetch("/object_info/LoraLoader");
  const info = await response.json();
  return info?.LoraLoader?.input?.required?.lora_name?.[0] || [];
}

function isLowQuality() {
  return (app.canvas.ds?.scale || 1) <= 0.5;
}

function fitString(ctx, str, maxWidth) {
  if (ctx.measureText(str).width <= maxWidth) return str;
  let result = String(str);
  while (result.length > 1 && ctx.measureText(`${result}…`).width > maxWidth) result = result.slice(0, -1);
  return `${result}…`;
}

function drawRoundedRectangle(ctx, options) {
  const lowQuality = isLowQuality();
  ctx.save();
  ctx.strokeStyle = options.colorStroke || LiteGraph.WIDGET_OUTLINE_COLOR;
  ctx.fillStyle = options.colorBackground || LiteGraph.WIDGET_BGCOLOR;
  ctx.beginPath();
  roundRect(ctx, options.pos[0], options.pos[1], options.size[0], options.size[1], lowQuality ? 0 : (options.borderRadius ?? options.size[1] * 0.5));
  ctx.fill();
  if (!lowQuality) ctx.stroke();
  ctx.restore();
}

function drawWidgetButton(ctx, options, text, isMouseDownedAndOver = false) {
  const borderRadius = isLowQuality() ? 0 : (options.borderRadius ?? 4);
  ctx.save();
  drawRoundedRectangle(ctx, {
    size: options.size,
    pos: [options.pos[0], options.pos[1] + (isMouseDownedAndOver ? 1 : 0)],
    borderRadius,
    colorBackground: isMouseDownedAndOver ? "#444" : LiteGraph.WIDGET_BGCOLOR,
    colorStroke: "transparent",
  });
  if (!isLowQuality()) {
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
    ctx.fillText(text, options.pos[0] + options.size[0] / 2, options.pos[1] + options.size[1] / 2 + (isMouseDownedAndOver ? 1 : 0));
  }
  ctx.restore();
}

function drawTogglePart(ctx, options) {
  const lowQuality = isLowQuality();
  ctx.save();
  const { posX, posY, height, value } = options;
  const toggleRadius = height * 0.36;
  const toggleBgWidth = height * 1.5;
  if (!lowQuality) {
    ctx.beginPath();
    roundRect(ctx, posX + 4, posY + 4, toggleBgWidth - 8, height - 8, height * 0.5);
    ctx.globalAlpha = app.canvas.editor_alpha * 0.25;
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.fill();
    ctx.globalAlpha = app.canvas.editor_alpha;
  }
  ctx.fillStyle = value === true ? "#89B" : "#888";
  const toggleX = lowQuality || value === false ? posX + height * 0.5 : value === true ? posX + height : posX + height * 0.75;
  ctx.beginPath();
  ctx.arc(toggleX, posY + height * 0.5, toggleRadius, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  return [posX, toggleBgWidth];
}

function drawNumberWidgetPart(ctx, options) {
  const arrowWidth = 9;
  const arrowHeight = 10;
  const innerMargin = 3;
  const numberWidth = 32;
  let posX = options.posX;
  const { posY, height, value } = options;
  const midY = posY + height / 2;
  if (options.direction === -1) posX = posX - arrowWidth - innerMargin - numberWidth - innerMargin - arrowWidth;

  ctx.save();
  ctx.fill(new Path2D(`M ${posX} ${midY} l ${arrowWidth} ${arrowHeight / 2} l 0 -${arrowHeight} L ${posX} ${midY} z`));
  const less = [posX, arrowWidth];
  posX += arrowWidth + innerMargin;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(fitString(ctx, Number(value).toFixed(2), numberWidth), posX + numberWidth / 2, midY);
  const number = [posX, numberWidth];
  posX += numberWidth + innerMargin;
  ctx.fill(new Path2D(`M ${posX} ${midY - arrowHeight / 2} l ${arrowWidth} ${arrowHeight / 2} l -${arrowWidth} ${arrowHeight / 2} v -${arrowHeight} z`));
  const more = [posX, arrowWidth];
  ctx.restore();
  return [less, number, more];
}

drawNumberWidgetPart.WIDTH_TOTAL = 56;

function roundRect(ctx, x, y, width, height, radius) {
  if (ctx.roundRect) {
    ctx.roundRect(x, y, width, height, radius);
  } else {
    ctx.rect(x, y, width, height);
  }
}

function boundsFromX(bounds, y, height) {
  return [bounds[0], y, bounds[1], height];
}

function inArea(pos, area) {
  if (!area) return false;
  return pos[0] >= area[0] && pos[0] <= area[0] + area[2] && pos[1] >= area[1] && pos[1] <= area[1] + area[3];
}

function roundStrengthStep(value) {
  return Math.round(Math.round(value * 20) * 5) / 100;
}

function roundDisplay(value) {
  return Math.round(value * 1000) / 1000;
}
