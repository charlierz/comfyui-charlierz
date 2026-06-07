import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";
import { ComfyWidgets } from "/scripts/widgets.js";
import { PromptHelperAutocomplete } from "./autocomplete.js";
import { CATEGORY_INPUTS } from "./data.js";

const extensionId = "charlierz.PromptHelperAutocomplete";
const autocomplete = new PromptHelperAutocomplete();

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
    this.search.placeholder = "Search tags, wildcard paths, or entries";
    searchBar.appendChild(this.search);

    this.filters = document.createElement("div");
    this.filters.className = "charlierz-wildcard-browser-filters";
    this.filterInputs = new Map();
    for (const [type, label, checked] of [
      ["wildcard", "Wildcards", true],
      ["wildcard_entry", "Entries", true],
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
    this.details.innerHTML = "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view entries and preview.</div>";
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
      const item = event.target.closest("[data-result-index]");
      if (!item) return;
      event.preventDefault();
      this.select(Number(item.dataset.resultIndex));
    });
    this.details.addEventListener("click", (event) => {
      const reroll = event.target.closest("[data-reroll-preview]");
      if (reroll) {
        event.preventDefault();
        this.previewSelected();
        return;
      }

      const selected = event.target.closest("[data-insert-selected]");
      if (selected) {
        event.preventDefault();
        if (this.insertSelected({ close: false })) flashInserted(selected);
        return;
      }

      const entry = event.target.closest("[data-insert-entry]");
      if (entry) {
        event.preventDefault();
        if (insertIntoWidget(this.node, "wildcard_text", entry.dataset.entryText)) {
          flashInserted(entry);
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
        summary.textContent = child.label;
        details.appendChild(summary);
        parent.appendChild(details);
        this.renderTreeNode(child, details, depth + 1);
        continue;
      }

      const index = this.items.push(child) - 1;
      const row = document.createElement("div");
      row.className = "charlierz-wildcard-browser-result charlierz-wildcard-browser-tree-leaf";
      row.dataset.resultIndex = `${index}`;
      row.style.paddingLeft = `${8 + depth * 14}px`;
      if (child === this.selected) row.classList.add("selected");

      const label = document.createElement("div");
      label.className = "charlierz-wildcard-browser-result-label";
      label.textContent = child.label;
      row.appendChild(label);

      const meta = document.createElement("div");
      meta.className = "charlierz-wildcard-browser-result-meta";
      meta.textContent = `${child.id} · ${child.entryCount} entries`;
      row.appendChild(meta);
      parent.appendChild(row);
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
      ["wildcard_entry", "Entries"],
      ["tag", "Tags"],
    ];
    for (const [type, title] of groups) {
      const entries = this.items
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.type === type);
      if (!entries.length) continue;

      const heading = document.createElement("div");
      heading.className = "charlierz-wildcard-browser-result-heading";
      heading.textContent = `${title} (${entries.length})`;
      this.results.appendChild(heading);

      for (const { item, index } of entries) {
        this.renderResultRow(item, index, this.results);
      }
    }
  }

  renderResultRow(item, index, parent) {
    const row = document.createElement("div");
    row.className = "charlierz-wildcard-browser-result";
    row.dataset.resultIndex = `${index}`;
    if (item === this.selected) row.classList.add("selected");

    const label = document.createElement("div");
    label.className = "charlierz-wildcard-browser-result-label";
    label.textContent = item.label ?? item.insertText ?? item.id;
    row.appendChild(label);

    const meta = document.createElement("div");
    meta.className = "charlierz-wildcard-browser-result-meta";
    meta.textContent = item.type === "wildcard_entry" ? `entry in ${item.wildcardLabel}` : item.id ?? item.category ?? item.type;
    row.appendChild(meta);
    parent.appendChild(row);
  }

  async select(index) {
    this.selected = this.items[index] ?? null;
    for (const row of this.results.querySelectorAll("[data-result-index]")) {
      row.classList.toggle("selected", Number(row.dataset.resultIndex) === index);
    }
    await this.renderDetails();
    this.previewSelected();
  }

  async renderDetails() {
    this.details.innerHTML = "";
    if (!this.selected) {
      this.details.innerHTML = "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view entries and preview.</div>";
      return;
    }

    const header = document.createElement("div");
    header.className = "charlierz-wildcard-browser-detail-header";

    const title = document.createElement("span");
    title.textContent = this.selected.label ?? this.selected.insertText ?? this.selected.id;
    header.appendChild(title);

    const actions = document.createElement("div");
    actions.className = "charlierz-wildcard-browser-detail-actions";

    const rerollButton = document.createElement("button");
    rerollButton.type = "button";
    rerollButton.dataset.rerollPreview = "true";
    rerollButton.textContent = "Reroll preview";
    actions.appendChild(rerollButton);

    const insertButton = document.createElement("button");
    insertButton.type = "button";
    insertButton.dataset.insertSelected = "true";
    insertButton.textContent = this.selected.type === "wildcard" ? "Insert wildcard ref" : "Insert selected text";
    actions.appendChild(insertButton);

    header.appendChild(actions);
    this.details.appendChild(header);

    this.previewOutput = document.createElement("pre");
    this.previewOutput.className = "charlierz-wildcard-browser-preview-output";
    this.previewOutput.textContent = "Preview will appear here.";
    this.details.appendChild(this.previewOutput);

    if (this.selected.type !== "wildcard") return;

    const url = new URL("/charlierz-prompt-catalog/wildcard", window.location.origin);
    url.searchParams.set("id", this.selected.id);
    const response = await api.fetchApi(`${url.pathname}${url.search}`);
    const detail = await response.json();
    if (!response.ok || detail.error) {
      this.details.insertAdjacentHTML(
        "beforeend",
        `<div class='charlierz-wildcard-browser-empty'>${detail.error || response.status}</div>`,
      );
      return;
    }

    const entriesTitle = document.createElement("div");
    entriesTitle.className = "charlierz-wildcard-browser-entries-title";
    entriesTitle.textContent = `Entries (${detail.entries.length})`;
    this.details.appendChild(entriesTitle);

    const entries = document.createElement("div");
    entries.className = "charlierz-wildcard-browser-entries";
    for (const entry of detail.entries) {
      const row = document.createElement("div");
      row.className = "charlierz-wildcard-browser-entry";

      const text = document.createElement("span");
      text.textContent = entry.weight !== 1 ? `${entry.text} (${entry.weight})` : entry.text;
      row.appendChild(text);

      const insert = document.createElement("button");
      insert.type = "button";
      insert.dataset.insertEntry = "true";
      insert.dataset.entryText = entry.text;
      insert.textContent = "Insert tag";
      row.appendChild(insert);
      entries.appendChild(row);
    }
    this.details.appendChild(entries);
  }

  async previewSelected() {
    if (!this.selected) return;
    const text = this.selected.type === "wildcard" ? this.selected.insertText : this.selected.insertText ?? this.selected.label;
    const response = await api.fetchApi("/charlierz-prompt-catalog/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, seed: Math.floor(Math.random() * 0xffffffff) }),
    });
    const result = await response.json();
    const output = this.previewOutput ?? this.details;
    if (!response.ok || result.error) {
      output.textContent = result.error || `Preview failed: ${response.status}`;
      return;
    }
    const diagnostics = result.diagnostics?.length ? `\n\nDiagnostics:\n${result.diagnostics.join("\n")}` : "";
    output.textContent = `${result.processedText ?? ""}${diagnostics}`;
  }

  insertSelected({ close = true } = {}) {
    if (!this.node || !this.selected) return false;
    const inserted = insertIntoWidget(this.node, "wildcard_text", this.selected.insertText ?? this.selected.label ?? "");
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
          searchContext: "wildcard",
          searchTypes: ["wildcard", "tag", "wildcard_entry"],
        });
      } else {
        autocomplete.attach(element, "general");
      }

      return result;
    };
  },
});
