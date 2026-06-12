import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";
import { ComfyWidgets } from "/scripts/widgets.js";
import { PromptHelperAutocomplete } from "./autocomplete.js";
import { CATEGORY_INPUTS, loadWildcardDetail } from "./data.js";

const extensionId = "charlierz.PromptHelperAutocomplete";
const autocomplete = new PromptHelperAutocomplete();
const wildcardPreviewTextareas = new WeakSet();

function loadCss() {
  const href = new URL("../css/prompt-helper.css", import.meta.url).href;
  if (document.querySelector(`link[href="${href}"]`)) return;

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function isPromptHelperWidget(node, inputName) {
  return (
    node?.comfyClass === "PromptHelper" && CATEGORY_INPUTS.includes(inputName)
  );
}

function isWildcardTemplateWidget(node, inputName) {
  return node?.comfyClass === "WildcardProcessor" && inputName === "wildcard_text";
}

function isAutocompleteElement(element) {
  return (
    element &&
    !element.readOnly &&
    (element.tagName === "TEXTAREA" ||
      (element.tagName === "INPUT" &&
        ["", "text", "search"].includes(element.type)))
  );
}

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name) ?? null;
}

function getWidgetValue(node, name) {
  return getWidget(node, name)?.value ?? "";
}

function setWidgetValue(node, name, value) {
  const widget = getWidget(node, name);
  if (!widget) return false;

  widget.value = value;
  const element = widget.element ?? widget.inputEl;
  if (element) {
    element.value = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }
  widget.callback?.(value);
  node.setDirtyCanvas?.(true, true);
  return true;
}

function commaSeparatedInsertion(current, start, end, text) {
  const before = current.slice(0, start);
  const after = current.slice(end);
  const needsPrefix = before.trim() && !before.trimEnd().endsWith(",");
  const prefix = needsPrefix ? ", " : before.endsWith(",") ? " " : "";
  const suffix = after.trim() && !after.trimStart().startsWith(",") ? ", " : "";
  return {
    next: `${before}${prefix}${text}${suffix}${after}`,
    cursor: before.length + prefix.length + text.length,
  };
}

function flashInserted(button) {
  if (!button) return;
  button.classList.add("charlierz-insert-flash");
  setTimeout(() => button.classList.remove("charlierz-insert-flash"), 140);
}

function attachWildcardProcessorPreview(element) {
  if (wildcardPreviewTextareas.has(element)) return;
  wildcardPreviewTextareas.add(element);

  element.addEventListener("click", (event) => {
    const ref = getWildcardRefAtCursor(element.value, element.selectionStart);
    if (!ref) {
      wildcardRefPreview.hide();
      return;
    }
    wildcardRefPreview.show(ref, event);
  });
}

function insertIntoWidget(node, name, text) {
  const widget = getWidget(node, name);
  if (!widget) return false;

  const element = widget.element ?? widget.inputEl;
  if (!element || typeof element.selectionStart !== "number") {
    const current = String(widget.value ?? "");
    const insertion = commaSeparatedInsertion(current, current.length, current.length, text);
    return setWidgetValue(node, name, insertion.next);
  }

  element.focus();
  const start = element.selectionStart;
  const end = element.selectionEnd;
  const current = String(widget.value ?? element.value ?? "");
  const insertion = commaSeparatedInsertion(current, start, end, text);
  setWidgetValue(node, name, insertion.next);
  element.setSelectionRange(insertion.cursor, insertion.cursor);
  return true;
}

function formatCompactNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return `${number}`;
}

function formatTagWeight(text, weight) {
  return weight !== 1 ? `${text} · ${formatCompactNumber(weight)}` : text;
}

function formatWildcardLabel(label, count) {
  return typeof count === "number" ? `${label} · ${count} tags` : label;
}

function getWildcardRefAtCursor(text, cursor) {
  const refPattern = /__([^\s,]+?)__/g;
  for (const match of text.matchAll(refPattern)) {
    const start = match.index ?? 0;
    const end = start + match[0].length;
    if (cursor < start || cursor > end) continue;

    const id = match[1].trim();
    if (!id || id.includes("__")) continue;
    return { id, start, end };
  }
  return null;
}

class WildcardRefPreview {
  constructor() {
    this.requestId = 0;
    this.root = document.createElement("div");
    this.root.className = "charlierz-wildcard-ref-preview";
    this.root.style.display = "none";
    document.body.appendChild(this.root);

    const hideOnOutsideInteraction = (event) => {
      if (this.root.style.display === "none") return;
      if (this.root.contains(event.target)) return;
      this.hide();
    };
    document.addEventListener("pointerdown", hideOnOutsideInteraction, true);
    document.addEventListener("mousedown", hideOnOutsideInteraction, true);
    document.addEventListener("click", hideOnOutsideInteraction, true);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.hide();
    });
  }

  hide() {
    this.requestId += 1;
    this.root.style.display = "none";
    this.root.innerHTML = "";
  }

  async show(ref, event) {
    const requestId = ++this.requestId;
    this.root.innerHTML = `<div class="charlierz-wildcard-ref-preview-loading">Loading ${ref.id}…</div>`;
    this.#position(event);
    this.root.style.display = "block";

    try {
      const detail = await loadWildcardDetail(ref.id);
      if (requestId !== this.requestId) return;
      this.#render(ref, detail);
      this.#position(event);
    } catch (error) {
      if (requestId !== this.requestId) return;
      console.error("[PromptHelper] Failed to load wildcard preview", error);
      this.root.innerHTML = `<div class="charlierz-wildcard-ref-preview-error">Wildcard not found: ${ref.id}</div>`;
      this.#position(event);
    }
  }

  #render(ref, detail) {
    const tags = detail.tags ?? [];
    const visibleTags = tags.slice(0, 80);
    this.root.innerHTML = "";

    const header = document.createElement("div");
    header.className = "charlierz-wildcard-ref-preview-header";
    header.textContent = formatWildcardLabel(ref.id, detail.tagCount ?? tags.length);
    this.root.appendChild(header);

    const list = document.createElement("div");
    list.className = "charlierz-wildcard-ref-preview-tags";
    for (const tag of visibleTags) {
      const row = document.createElement("div");
      row.textContent = formatTagWeight(tag.text, tag.weight);
      list.appendChild(row);
    }
    this.root.appendChild(list);

    if (tags.length > visibleTags.length) {
      const more = document.createElement("div");
      more.className = "charlierz-wildcard-ref-preview-more";
      more.textContent = `Showing first ${visibleTags.length}`;
      this.root.appendChild(more);
    }
  }

  #position(event) {
    const margin = 8;
    const rect = this.root.getBoundingClientRect();
    const left = Math.min(
      Math.max(event.clientX + margin, margin),
      window.innerWidth - rect.width - margin,
    );
    const top = Math.min(
      Math.max(event.clientY + margin, margin),
      window.innerHeight - rect.height - margin,
    );
    this.root.style.left = `${left}px`;
    this.root.style.top = `${top}px`;
  }
}

const wildcardRefPreview = new WildcardRefPreview();

function addReadOnlyTextWidget(node, name) {
  const result = ComfyWidgets.STRING(
    node,
    name,
    ["STRING", { multiline: true }],
    app,
  );
  const widget = result.widget;
  const element = widget.element ?? widget.inputEl;
  if (element) element.readOnly = true;
  widget.serializeValue = async () => "";
  return widget;
}

function setComboWidgetValues(widget, values) {
  widget.options ??= {};
  widget.options.values = values;
  if (!values.includes(widget.value)) {
    widget.value = values[0] ?? "";
  }
}

function getLlamaCppModelsData(result) {
  const models = Array.isArray(result)
    ? result
    : result.data || result.models || [];
  return models.filter((model) => model && typeof model === "object");
}

function getLlamaCppModelDisplayName(model) {
  const firstAlias = Array.isArray(model.aliases) ? model.aliases[0] : "";
  return String(
    firstAlias || model.id || model.model || model.name || "",
  ).trim();
}

function llamaCppModelSupportsImage(model) {
  return model.architecture?.input_modalities?.includes("image") === true;
}

async function reloadLlamaCppModels(node) {
  const serverUrl =
    getWidgetValue(node, "server_url") || "http://127.0.0.1:8080";
  const params = new URLSearchParams({ server_url: serverUrl });

  const response = await api.fetchApi(
    `/charlierz-llama-cpp/models?${params.toString()}`,
  );
  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(
      result.error || `Model reload failed with HTTP ${response.status}`,
    );
  }

  const models = getLlamaCppModelsData(result)
    .filter(
      (model) =>
        node.comfyClass !== "LlamaCppVisionChat" ||
        llamaCppModelSupportsImage(model),
    )
    .map(getLlamaCppModelDisplayName)
    .filter(Boolean);

  const modelWidget = node.widgets?.find((widget) => widget.name === "model");
  if (!modelWidget) {
    throw new Error("Model widget not found");
  }
  setComboWidgetValues(modelWidget, models);
  node.setDirtyCanvas(true, true);
}

async function previewWildcardProcessor(node, { reroll = false } = {}) {
  if (reroll) {
    setWidgetValue(node, "seed", Math.floor(Math.random() * 0xffffffff));
  }

  const response = await api.fetchApi("/charlierz-prompt-catalog/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: getWidgetValue(node, "wildcard_text"),
      seed: getWidgetValue(node, "seed") || 0,
      weightMode: getWidgetValue(node, "weight_mode") || "count",
    }),
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(result.error || `Preview failed with HTTP ${response.status}`);
  }

  const diagnostics = result.diagnostics?.length
    ? `\n\nDiagnostics:\n${result.diagnostics.join("\n")}`
    : "";
  setWidgetValue(node, "preview_text", `${result.processedText ?? ""}${diagnostics}`);
}

class WildcardBrowser {
  constructor() {
    this.node = null;
    this.selected = null;
    this.searchTimer = null;
    this.items = [];

    this.root = document.createElement("div");
    this.root.className = "charlierz-wildcard-browser";
    this.root.style.display = "none";

    this.dialog = document.createElement("div");
    this.dialog.className = "charlierz-wildcard-browser-dialog";
    this.root.appendChild(this.dialog);

    const header = document.createElement("div");
    header.className = "charlierz-wildcard-browser-header";
    header.textContent = "Wildcard Browser";
    this.closeButton = document.createElement("button");
    this.closeButton.type = "button";
    this.closeButton.textContent = "×";
    header.appendChild(this.closeButton);
    this.dialog.appendChild(header);

    const searchBar = document.createElement("div");
    searchBar.className = "charlierz-wildcard-browser-searchbar";
    this.search = document.createElement("input");
    this.search.className = "charlierz-wildcard-browser-search";
    this.search.type = "search";
    this.search.placeholder = "Search tags or wildcard paths";
    searchBar.appendChild(this.search);

    this.filters = document.createElement("div");
    this.filters.className = "charlierz-wildcard-browser-filters";
    this.filterInputs = new Map();
    for (const [type, label, checked] of [
      ["wildcard", "Wildcards", true],
      ["tag", "Tags", false],
    ]) {
      const filterLabel = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = type;
      input.checked = checked;
      this.filterInputs.set(type, input);
      filterLabel.appendChild(input);
      filterLabel.appendChild(document.createTextNode(label));
      this.filters.appendChild(filterLabel);
    }
    searchBar.appendChild(this.filters);
    this.dialog.appendChild(searchBar);

    const body = document.createElement("div");
    body.className = "charlierz-wildcard-browser-body";
    this.results = document.createElement("div");
    this.results.className = "charlierz-wildcard-browser-results";
    this.details = document.createElement("div");
    this.details.className = "charlierz-wildcard-browser-details";
    this.details.innerHTML = "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view tags and preview.</div>";
    body.appendChild(this.results);
    body.appendChild(this.details);
    this.dialog.appendChild(body);

    document.body.appendChild(this.root);

    this.closeButton.addEventListener("click", () => this.hide());
    this.root.addEventListener("mousedown", (event) => {
      if (event.target === this.root) this.hide();
    });
    this.search.addEventListener("input", () => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => this.runSearch(), 150);
    });
    this.filters.addEventListener("change", () => this.runSearch());
    this.results.addEventListener("mousedown", (event) => {
      const insert = event.target.closest("[data-insert-result]");
      if (insert) {
        event.preventDefault();
        event.stopPropagation();
        const item = this.items[Number(insert.dataset.resultIndex)];
        if (this.insertItem(item, { close: false })) flashInserted(insert);
        return;
      }

      const item = event.target.closest("[data-result-index]");
      if (!item) return;
      event.preventDefault();
      this.select(Number(item.dataset.resultIndex));
    });
    this.results.addEventListener("click", (event) => {
      if (!event.target.closest("[data-insert-result]")) return;
      event.preventDefault();
      event.stopPropagation();
    });
    this.details.addEventListener("click", (event) => {
      const selected = event.target.closest("[data-insert-selected]");
      if (selected) {
        event.preventDefault();
        if (this.insertSelected({ close: false })) flashInserted(selected);
        return;
      }

      const tag = event.target.closest("[data-insert-tag]");
      if (tag) {
        event.preventDefault();
        if (insertIntoWidget(this.node, "wildcard_text", tag.dataset.tagText)) {
          flashInserted(tag);
        }
      }
    });
  }

  show(node) {
    this.node = node;
    this.selected = null;
    this.root.style.display = "flex";
    this.search.focus();
    this.loadTree();
  }

  hide() {
    this.root.style.display = "none";
    this.node = null;
    this.selected = null;
  }

  async loadTree() {
    const response = await api.fetchApi("/charlierz-prompt-catalog/wildcards");
    const result = await response.json();
    if (!response.ok || result.error) {
      this.results.innerHTML = `<div class='charlierz-wildcard-browser-empty'>${result.error || response.status}</div>`;
      return;
    }

    this.items = [];
    this.results.innerHTML = "";
    this.renderTreeNode(result.tree, this.results, 0);
  }

  async runSearch() {
    const query = this.search.value.trim();
    if (!query) {
      this.loadTree();
      return;
    }

    const types = [...this.filterInputs.entries()]
      .filter(([_type, input]) => input.checked)
      .map(([type]) => type);
    if (!types.length) {
      this.results.innerHTML = "<div class='charlierz-wildcard-browser-empty'>Select at least one result type.</div>";
      return;
    }

    const url = new URL("/charlierz-prompt-catalog/search", window.location.origin);
    url.searchParams.set("q", query);
    url.searchParams.set("context", "wildcard");
    url.searchParams.set("types", types.join(","));
    url.searchParams.set("limit", "120");

    const response = await api.fetchApi(`${url.pathname}${url.search}`);
    const result = await response.json();
    if (!response.ok || result.error) {
      this.results.innerHTML = `<div class='charlierz-wildcard-browser-empty'>${result.error || response.status}</div>`;
      return;
    }

    this.items = result.results ?? [];
    this.renderGroupedResults();
  }

  renderTreeNode(node, parent, depth) {
    if (!node) return;
    for (const child of node.children ?? []) {
      if (child.type === "directory") {
        const details = document.createElement("details");
        details.className = "charlierz-wildcard-browser-tree-group";
        details.open = depth < 1;
        const summary = document.createElement("summary");
        const summaryLabel = document.createElement("span");
        summaryLabel.className = "charlierz-wildcard-browser-summary-label";
        summaryLabel.textContent = child.id ? formatWildcardLabel(child.label, child.tagCount) : child.label;
        summary.appendChild(summaryLabel);

        if (child.id) {
          const index = this.items.push(child) - 1;
          const insert = document.createElement("button");
          insert.type = "button";
          insert.className = "charlierz-wildcard-browser-row-insert";
          insert.dataset.insertResult = "true";
          insert.dataset.resultIndex = `${index}`;
          insert.textContent = "Insert wildcard";
          insert.title = "Insert wildcard";
          summary.appendChild(insert);
        }

        details.appendChild(summary);
        parent.appendChild(details);
        this.renderTreeNode(child, details, depth + 1);
        continue;
      }

      const index = this.items.push(child) - 1;
      this.renderResultRow(child, index, parent, {
        className: "charlierz-wildcard-browser-tree-leaf",
        paddingLeft: 8 + depth * 14,
      });
    }
  }

  renderGroupedResults() {
    this.results.innerHTML = "";
    if (!this.items.length) {
      this.results.innerHTML = "<div class='charlierz-wildcard-browser-empty'>No results.</div>";
      return;
    }

    const groups = [
      ["wildcard", "Wildcards"],
      ["tag", "Tags"],
    ];
    for (const [type, title] of groups) {
      const results = this.items
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.type === type);
      if (!results.length) continue;

      const heading = document.createElement("div");
      heading.className = "charlierz-wildcard-browser-result-heading";
      heading.textContent = `${title} (${results.length})`;
      this.results.appendChild(heading);

      for (const { item, index } of results) {
        this.renderResultRow(item, index, this.results, { showPath: true });
      }
    }
  }

  renderResultRow(item, index, parent, options = {}) {
    const row = document.createElement("div");
    row.className = `charlierz-wildcard-browser-result ${options.className ?? ""}`.trim();
    row.dataset.resultIndex = `${index}`;
    if (typeof options.paddingLeft === "number") row.style.paddingLeft = `${options.paddingLeft}px`;
    if (item === this.selected) row.classList.add("selected");

    const content = document.createElement("div");
    content.className = "charlierz-wildcard-browser-result-content";

    const label = document.createElement("div");
    label.className = "charlierz-wildcard-browser-result-label";
    const defaultLabel = item.type === "wildcard" && item.tagCount
      ? formatWildcardLabel(item.label ?? item.id, item.tagCount)
      : item.label ?? item.insertText ?? item.id;
    label.textContent = options.label ?? defaultLabel;
    content.appendChild(label);

    if (options.showPath && item.type === "wildcard" && item.id) {
      const meta = document.createElement("div");
      meta.className = "charlierz-wildcard-browser-result-meta";
      meta.textContent = item.id;
      content.appendChild(meta);
    } else if (item.type !== "wildcard") {
      const meta = document.createElement("div");
      meta.className = "charlierz-wildcard-browser-result-meta";
      meta.textContent = item.category ?? item.type;
      content.appendChild(meta);
    }

    row.appendChild(content);

    if (item.type === "wildcard") {
      const insert = document.createElement("button");
      insert.type = "button";
      insert.className = "charlierz-wildcard-browser-row-insert";
      insert.dataset.insertResult = "true";
      insert.dataset.resultIndex = `${index}`;
      insert.textContent = "Insert wildcard";
      insert.title = "Insert wildcard";
      row.appendChild(insert);
    }

    parent.appendChild(row);
  }

  async select(index) {
    this.selected = this.items[index] ?? null;
    for (const row of this.results.querySelectorAll("[data-result-index]")) {
      row.classList.toggle("selected", Number(row.dataset.resultIndex) === index);
    }
    await this.renderDetails();
  }

  async renderDetails() {
    this.details.innerHTML = "";
    if (!this.selected) {
      this.details.innerHTML = "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view tags and preview.</div>";
      return;
    }

    let detail = null;
    if (this.selected.type === "wildcard") {
      const url = new URL("/charlierz-prompt-catalog/wildcard", window.location.origin);
      url.searchParams.set("id", this.selected.id);
      const response = await api.fetchApi(`${url.pathname}${url.search}`);
      detail = await response.json();
      if (!response.ok || detail.error) {
        this.details.insertAdjacentHTML(
          "beforeend",
          `<div class='charlierz-wildcard-browser-empty'>${detail.error || response.status}</div>`,
        );
        return;
      }
    }

    const header = document.createElement("div");
    header.className = "charlierz-wildcard-browser-detail-header";

    const title = document.createElement("span");
    const titleText = this.selected.label ?? this.selected.insertText ?? this.selected.id;
    title.textContent = detail ? formatWildcardLabel(titleText, detail.tagCount ?? detail.tags.length) : titleText;
    header.appendChild(title);

    const actions = document.createElement("div");
    actions.className = "charlierz-wildcard-browser-detail-actions";

    const insertButton = document.createElement("button");
    insertButton.type = "button";
    insertButton.dataset.insertSelected = "true";
    insertButton.textContent = this.selected.type === "wildcard" ? "Insert wildcard" : "Insert selected text";
    actions.appendChild(insertButton);

    header.appendChild(actions);
    this.details.appendChild(header);

    if (!detail) return;

    const tags = document.createElement("div");
    tags.className = "charlierz-wildcard-browser-tags";
    for (const tag of detail.tags) {
      const row = document.createElement("div");
      row.className = "charlierz-wildcard-browser-tag";
      row.dataset.insertTag = "true";
      row.dataset.tagText = tag.text;
      row.title = "Insert tag";

      const text = document.createElement("span");
      text.textContent = formatTagWeight(tag.text, tag.weight);
      row.appendChild(text);
      tags.appendChild(row);
    }
    this.details.appendChild(tags);
  }

  insertSelected({ close = true } = {}) {
    return this.insertItem(this.selected, { close });
  }

  insertItem(item, { close = true } = {}) {
    if (!this.node || !item) return false;
    const inserted = insertIntoWidget(this.node, "wildcard_text", item.insertText ?? item.label ?? "");
    if (inserted && close) this.hide();
    return inserted;
  }
}

const wildcardBrowser = new WildcardBrowser();

async function unloadLlamaCppModel(node) {
  const serverUrl =
    getWidgetValue(node, "server_url") || "http://127.0.0.1:8080";
  const model = String(getWidgetValue(node, "model") || "").trim();
  if (!model) {
    alert("Missing llama.cpp model");
    return;
  }

  const response = await api.fetchApi("/charlierz-llama-cpp/unload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ server_url: serverUrl, model }),
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(
      result.error || `Unload failed with HTTP ${response.status}`,
    );
  }
}

app.registerExtension({
  name: extensionId,
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "EstimateTextTokens") {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        this.tokenEstimateWidget = addReadOnlyTextWidget(
          this,
          "token_estimate",
        );
      };

      const originalOnExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (message) {
        originalOnExecuted?.apply(this, arguments);
        if (this.tokenEstimateWidget && message.text?.[0]) {
          this.tokenEstimateWidget.value = message.text[0];
        }
      };
      return;
    }

    if (nodeData.name === "WildcardProcessor") {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        this.addWidget("button", "Browse Wildcards", null, () => {
          wildcardBrowser.show(this);
        });
        this.addWidget("button", "Preview / Reroll", null, async () => {
          try {
            await previewWildcardProcessor(this, { reroll: true });
          } catch (error) {
            console.error(error);
            alert(error.message || String(error));
          }
        });
      };
      return;
    }

    if (!["LlamaCppChat", "LlamaCppVisionChat"].includes(nodeData.name)) return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      originalOnNodeCreated?.apply(this, arguments);
      this.addWidget("button", "Reload Models", null, async () => {
        try {
          await reloadLlamaCppModels(this);
        } catch (error) {
          console.error(error);
          alert(error.message || String(error));
        }
      });
      this.addWidget("button", "Unload Model", null, async () => {
        try {
          await unloadLlamaCppModel(this);
        } catch (error) {
          console.error(error);
          alert(error.message || String(error));
        }
      });
    };
  },

  setup() {
    loadCss();

    const originalStringWidget = ComfyWidgets.STRING;
    ComfyWidgets.STRING = function (node, inputName, inputData, appInstance) {
      const result = originalStringWidget.apply(this, arguments);

      const element = result?.widget?.element ?? result?.widget?.inputEl;
      if (!isAutocompleteElement(element)) return result;

      if (isPromptHelperWidget(node, inputName)) {
        const prioritySources = [
          { source: inputName, className: "category-priority-match" },
        ];
        if (inputName === "themes_roles") {
          prioritySources.unshift(
            { source: "characters", className: "character-priority-match" },
            { source: "copyrights", className: "copyright-priority-match" },
          );
        }

        autocomplete.attach(element, "general", {
          enableRelatedTags: true,
          relatedCategory: inputName,
          prioritySources,
          node,
          categoryName: inputName,
        });
      } else if (isWildcardTemplateWidget(node, inputName)) {
        autocomplete.attach(element, "general", {
          enableRelatedTags: false,
          searchContext: "wildcard",
          searchTypes: ["wildcard", "tag"],
        });
        attachWildcardProcessorPreview(element);
      } else {
        autocomplete.attach(element, "general");
      }

      return result;
    };
  },
});
