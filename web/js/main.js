import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";
import { ComfyWidgets } from "/scripts/widgets.js";
import { PromptHelperAutocomplete } from "./autocomplete.js";
import {
  decomposePromptText,
  deletePrompt,
  loadPromptCategories,
  loadPromptDetail,
  loadPrompts,
  loadWildcardDetail,
  renamePrompt,
  savePrompt,
  searchPrompts,
} from "./data.js";

const extensionId = "charlierz.PromptHelperAutocomplete";
const autocomplete = new PromptHelperAutocomplete();
const wildcardPreviewTextareas = new WeakSet();
const LAST_WILDCARD_SEED_PROPERTY = "charlierzLastWildcardSeed";
const LAST_PREVIEW_TEXT_PROPERTY = "charlierzLastPreviewText";
let promptCategories = [];
let promptCategoryIds = new Set();
let promptCategorySourceMap = new Map();
const promptHelperFocusedCategory = new WeakMap();

function loadCss() {
  const href = new URL("../css/prompt-helper.css", import.meta.url).href;
  if (document.querySelector(`link[href="${href}"]`)) return;

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function isPromptHelperNode(node) {
  return node?.comfyClass === "PromptHelper";
}

function isPromptHelperWidget(node, inputName) {
  return isPromptHelperNode(node) && promptCategoryIds.has(inputName);
}

function hasPromptCategorySource(inputName, source) {
  return promptCategorySourceMap.get(inputName)?.includes(source) ?? false;
}

function isWildcardTemplateWidget(node, inputName) {
  return (
    node?.comfyClass === "WildcardProcessor" && inputName === "wildcard_text"
  );
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

function ensureNodeProperties(node) {
  node.properties ??= {};
  return node.properties;
}

function setNodeProperty(node, key, value) {
  ensureNodeProperties(node)[key] = value;
  node.setDirtyCanvas?.(true, true);
}

function getFirstUiValue(message, key) {
  const value = message?.[key];
  if (Array.isArray(value)) return value[0];
  return value;
}

function addActionButton(node, label, callback) {
  const widget = node.addWidget("button", label, null, callback);
  widget.serialize = false;
  return widget;
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

function blockInsertion(current, start, end, text) {
  const before = current.slice(0, start);
  const after = current.slice(end);
  const trimmedText = String(text ?? "").trim();
  const prefix = before.trim()
    ? before.endsWith("\n\n")
      ? ""
      : before.endsWith("\n")
        ? "\n"
        : "\n\n"
    : "";
  const suffix = after.trim()
    ? after.startsWith("\n\n")
      ? ""
      : after.startsWith("\n")
        ? "\n"
        : "\n\n"
    : "";
  return {
    next: `${before}${prefix}${trimmedText}${suffix}${after}`,
    cursor: before.length + prefix.length + trimmedText.length,
  };
}

function flashInserted(button) {
  if (!button) return;
  button.classList.add("charlierz-insert-flash");
  setTimeout(() => button.classList.remove("charlierz-insert-flash"), 140);
}

function getPromptHelperFocusedCategory(node) {
  const focused = promptHelperFocusedCategory.get(node);
  if (focused && promptCategoryIds.has(focused)) return focused;
  return promptCategories[0]?.id ?? null;
}

function getPromptHelperText(node) {
  return promptCategories
    .map((category) => String(getWidgetValue(node, category.id) ?? "").trim())
    .filter(Boolean)
    .join("\n\n");
}

function getPromptHelperCategories(node) {
  return Object.fromEntries(
    promptCategories.map((category) => [
      category.id,
      String(getWidgetValue(node, category.id) ?? "").trim(),
    ]),
  );
}

function clearPromptHelper(node) {
  if (!isPromptHelperNode(node)) return false;
  let changed = false;
  for (const category of promptCategories) {
    if (String(getWidgetValue(node, category.id) ?? "") === "") continue;
    changed = setWidgetValue(node, category.id, "") || changed;
  }
  return changed;
}

function attachWildcardProcessorPreview(element) {
  if (wildcardPreviewTextareas.has(element)) return;
  wildcardPreviewTextareas.add(element);

  const hideForTextEdit = (event) => {
    if (
      event.type === "keydown" &&
      (event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        (event.key.length > 1 &&
          !["Backspace", "Delete", "Space"].includes(event.key)))
    ) {
      return;
    }

    wildcardRefPreview.hide();
  };

  element.addEventListener("beforeinput", hideForTextEdit, true);
  element.addEventListener("input", hideForTextEdit);
  element.addEventListener("keydown", hideForTextEdit, true);

  element.addEventListener("click", (event) => {
    const ref = getWildcardRefAtCursor(element.value, element.selectionStart);
    if (!ref) {
      wildcardRefPreview.hide();
      return;
    }
    wildcardRefPreview.show(ref, event);
  });
}

function insertIntoWidget(node, name, text, { mode = "comma" } = {}) {
  const widget = getWidget(node, name);
  if (!widget) return false;

  const element = widget.element ?? widget.inputEl;
  if (!element || typeof element.selectionStart !== "number") {
    const current = String(widget.value ?? "");
    const insert = mode === "block" ? blockInsertion : commaSeparatedInsertion;
    const insertion = insert(current, current.length, current.length, text);
    return setWidgetValue(node, name, insertion.next);
  }

  element.focus();
  const start = element.selectionStart;
  const end = element.selectionEnd;
  const current = String(widget.value ?? element.value ?? "");
  const insert = mode === "block" ? blockInsertion : commaSeparatedInsertion;
  const insertion = insert(current, start, end, text);
  setWidgetValue(node, name, insertion.next);
  element.setSelectionRange(insertion.cursor, insertion.cursor);
  return true;
}

function insertIntoPromptHelper(
  node,
  text,
  { mode = "comma", category = null, forceFocused = false } = {},
) {
  const targetCategory =
    !forceFocused && category && promptCategoryIds.has(category)
      ? category
      : getPromptHelperFocusedCategory(node);
  if (!targetCategory) return false;
  return insertIntoWidget(node, targetCategory, text, { mode });
}

function normalizePromptToken(token) {
  return String(token ?? "")
    .trim()
    .replace(/^\((.*):[0-9]+(?:\.[0-9]+)?\)$/, "$1")
    .replace(/:[0-9]+(?:\.[0-9]+)?$/, "")
    .replaceAll(" ", "_");
}

function getExistingPromptHelperCategoryTokens(node, category) {
  return new Set(
    String(getWidgetValue(node, category) ?? "")
      .split(/[\n,]/)
      .map(normalizePromptToken)
      .filter(Boolean),
  );
}

function filterNewPromptHelperTags(node, category, tags) {
  const existing = getExistingPromptHelperCategoryTokens(node, category);
  const accepted = [];
  for (const tag of tags ?? []) {
    const normalized = normalizePromptToken(tag);
    if (!normalized || existing.has(normalized)) continue;
    existing.add(normalized);
    accepted.push(tag);
  }
  return accepted;
}

function appendPromptCategories(node, categories) {
  let inserted = false;
  for (const [category, text] of Object.entries(categories ?? {})) {
    if (!promptCategoryIds.has(category) || !String(text).trim()) continue;
    inserted =
      insertIntoPromptHelper(node, text, {
        mode: "block",
        category,
        forceFocused: false,
      }) || inserted;
  }
  return inserted;
}

function appendDecomposedPrompt(
  node,
  decomposition,
  { focusedText = "" } = {},
) {
  let inserted = false;
  for (const [category, tags] of Object.entries(
    decomposition.categories ?? {},
  )) {
    if (!promptCategoryIds.has(category) || !tags?.length) continue;
    const newTags = filterNewPromptHelperTags(node, category, tags);
    if (!newTags.length) continue;
    inserted =
      insertIntoPromptHelper(node, newTags.join(", "), {
        category,
        forceFocused: false,
      }) || inserted;
  }

  const focusedCategory = getPromptHelperFocusedCategory(node);
  const uncategorized = filterNewPromptHelperTags(
    node,
    focusedCategory,
    decomposition.uncategorized ?? [],
  );
  if (uncategorized.length) {
    inserted =
      insertIntoPromptHelper(node, uncategorized.join(", "), {
        forceFocused: true,
      }) || inserted;
  }
  return inserted;
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
    header.textContent = formatWildcardLabel(
      ref.id,
      detail.tagCount ?? tags.length,
    );
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

function setLlamaCppModelWidgetValues(node, widget, values) {
  if (Array.isArray(widget.options?.values)) {
    widget.options.values = values;
    if (!values.includes(widget.value)) {
      setWidgetValue(node, widget.name, values[0] ?? "");
    }
    return;
  }

  if (!values.includes(widget.value)) {
    setWidgetValue(node, widget.name, values[0] ?? "");
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
  setLlamaCppModelWidgetValues(node, modelWidget, models);
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
      weightMode: getWidgetValue(node, "weight_mode") || "sqrt",
    }),
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(
      result.error || `Preview failed with HTTP ${response.status}`,
    );
  }

  const diagnostics = result.diagnostics?.length
    ? `\n\nDiagnostics:\n${result.diagnostics.join("\n")}`
    : "";
  setWidgetValue(
    node,
    "preview_text",
    `${result.processedText ?? ""}${diagnostics}`,
  );
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
    header.textContent = "Prompt Catalog";
    this.closeButton = document.createElement("button");
    this.closeButton.type = "button";
    this.closeButton.textContent = "×";
    header.appendChild(this.closeButton);
    this.dialog.appendChild(header);

    this.activeTab = "prompts";
    this.promptDirty = false;
    this.promptSelected = null;
    this.promptLoadedText = "";

    this.tabs = document.createElement("div");
    this.tabs.className = "charlierz-wildcard-browser-tabs";
    this.promptsTabButton = document.createElement("button");
    this.promptsTabButton.type = "button";
    this.promptsTabButton.textContent = "Prompts";
    this.wildcardsTabButton = document.createElement("button");
    this.wildcardsTabButton.type = "button";
    this.wildcardsTabButton.textContent = "Wildcards";
    this.tabs.appendChild(this.promptsTabButton);
    this.tabs.appendChild(this.wildcardsTabButton);
    this.dialog.appendChild(this.tabs);

    const searchBar = document.createElement("div");
    searchBar.className = "charlierz-wildcard-browser-searchbar";
    this.search = document.createElement("input");
    this.search.className = "charlierz-wildcard-browser-search";
    this.search.type = "search";
    this.search.placeholder = "Search prompt names or text";
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
    this.decomposePromptLabel = document.createElement("label");
    this.decomposePromptLabel.className = "charlierz-prompt-decompose-toggle";
    this.decomposePromptInput = document.createElement("input");
    this.decomposePromptInput.type = "checkbox";
    this.decomposePromptInput.checked = true;
    this.decomposePromptLabel.appendChild(this.decomposePromptInput);
    this.decomposePromptLabel.appendChild(
      document.createTextNode("Decompose into categories"),
    );
    this.dialog.appendChild(searchBar);

    this.body = document.createElement("div");
    this.body.className = "charlierz-wildcard-browser-body";
    this.results = document.createElement("div");
    this.results.className = "charlierz-wildcard-browser-results";
    this.details = document.createElement("div");
    this.details.className = "charlierz-wildcard-browser-details";
    this.details.innerHTML =
      "<div class='charlierz-wildcard-browser-empty'>Select a prompt to edit, or create a new one.</div>";
    this.body.appendChild(this.results);
    this.body.appendChild(this.details);
    this.dialog.appendChild(this.body);

    this.promptLibraryActions = this.createPromptActionGroup("Prompt file", [
      ["new", "New"],
      ["save", "Save"],
      ["delete", "Delete"],
    ]);
    this.promptEditorActions = this.createPromptActionGroup("Node text boxes", [
      ["newCurrent", "Load from Node"],
      ["insert", "Insert into Node"],
      ["replace", "Replace Node"],
      ["clear", "Clear Node"],
    ]);
    this.promptPreviewActions = this.createPromptActionGroup("Preview", [
      ["preview", "Preview / Reroll"],
    ]);
    this.promptActionGroups = [
      this.promptLibraryActions,
      this.promptEditorActions,
      this.promptPreviewActions,
    ];
    this.promptIdInput = document.createElement("input");
    this.promptIdInput.className = "charlierz-prompt-id-input";
    this.promptIdInput.placeholder = "prompt/id";
    this.promptEditor = document.createElement("textarea");
    this.promptEditor.className = "charlierz-prompt-editor";
    this.promptEditor.placeholder =
      "Write prompt text with tags, {variants}, and __wildcards__...";
    this.promptEditor.title =
      "Editing text clears hidden category-aware metadata for this prompt. Use Load from Node to preserve node categories before saving.";
    this.promptPreview = document.createElement("pre");
    this.promptPreview.className = "charlierz-prompt-preview";
    this.promptPreview.textContent = "Preview output appears here.";
    autocomplete.attach(this.promptEditor, "general", {
      enableRelatedTags: false,
      searchContext: "wildcard",
      searchTypes: ["wildcard", "tag"],
    });
    attachWildcardProcessorPreview(this.promptEditor);

    document.body.appendChild(this.root);

    this.closeButton.addEventListener("click", () => this.hide());
    this.root.addEventListener("mousedown", (event) => {
      if (event.target === this.root) this.hide();
    });
    this.search.addEventListener("input", () => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => this.runSearch(), 150);
    });
    this.wildcardsTabButton.addEventListener("click", () =>
      this.setTab("wildcards"),
    );
    this.promptsTabButton.addEventListener("click", () =>
      this.setTab("prompts"),
    );
    this.filters.addEventListener("change", () => this.runSearch());
    this.results.addEventListener("mousedown", async (event) => {
      const insert = event.target.closest("[data-insert-result]");
      if (insert) {
        event.preventDefault();
        event.stopPropagation();
        const item = this.items[Number(insert.dataset.resultIndex)];
        if (await this.insertItem(item, { close: false }))
          flashInserted(insert);
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
    this.promptEditor.addEventListener("input", () => {
      this.promptDirty = this.promptEditor.value !== this.promptLoadedText;
      if (this.promptDirty) this.promptCategoriesValue = null;
    });
    for (const actionGroup of this.promptActionGroups) {
      actionGroup.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-prompt-action]");
        if (!button) return;
        event.preventDefault();
        try {
          await this.runPromptAction(button.dataset.promptAction, button);
        } catch (error) {
          console.error(error);
          alert(error.message || String(error));
        }
      });
    }
    this.details.addEventListener("click", async (event) => {
      const selected = event.target.closest("[data-insert-selected]");
      if (selected) {
        event.preventDefault();
        if (await this.insertSelected({ close: false }))
          flashInserted(selected);
        return;
      }

      const tag = event.target.closest("[data-insert-tag]");
      if (tag) {
        event.preventDefault();
        if (
          this.insertText(tag.dataset.tagText, {
            category: tag.dataset.promptCategory || null,
          })
        ) {
          flashInserted(tag);
        }
      }
    });
  }

  createPromptActionGroup(title, actions) {
    const group = document.createElement("div");
    group.className = "charlierz-prompt-browser-action-group";

    const header = document.createElement("div");
    header.className = "charlierz-prompt-browser-action-header";

    const heading = document.createElement("div");
    heading.className = "charlierz-prompt-browser-action-heading";
    heading.textContent = title;
    header.appendChild(heading);

    const buttons = document.createElement("div");
    buttons.className = "charlierz-prompt-browser-action-buttons";
    for (const [name, label] of actions) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.promptAction = name;
      button.textContent = label;
      buttons.appendChild(button);
    }
    header.appendChild(buttons);
    group.appendChild(header);
    return group;
  }

  show(node) {
    this.node = node;
    this.activeTab = "prompts";
    this.selected = null;
    this.search.value = "";
    this.root.style.display = "flex";
    this.search.focus();
    this.loadTree();
  }

  hide() {
    if (!this.canDiscardPromptEdits()) return;
    this.root.style.display = "none";
    this.node = null;
    this.selected = null;
  }

  canDiscardPromptEdits() {
    return (
      this.activeTab !== "prompts" ||
      !this.promptDirty ||
      confirm("Discard unsaved prompt changes?")
    );
  }

  setTab(tab) {
    if (tab === this.activeTab) return;
    if (!this.canDiscardPromptEdits()) return;
    this.activeTab = tab;
    this.selected = null;
    this.promptDirty = false;
    this.promptLoadedText = "";
    this.promptSelected = null;
    this.promptCategoriesValue = null;
    this.search.value = "";
    this.updateTabUi();
    this.loadTree();
  }

  updateTabUi() {
    this.wildcardsTabButton.classList.toggle(
      "active",
      this.activeTab === "wildcards",
    );
    this.promptsTabButton.classList.toggle(
      "active",
      this.activeTab === "prompts",
    );
    this.filters.style.display =
      this.activeTab === "wildcards" ? "flex" : "none";
    this.body.classList.toggle(
      "charlierz-wildcard-browser-body-prompts",
      this.activeTab === "prompts",
    );
    for (const group of this.promptActionGroups) {
      group.style.display = this.activeTab === "prompts" ? "block" : "none";
    }
    this.decomposePromptLabel.style.display =
      this.activeTab === "prompts" && isPromptHelperNode(this.node)
        ? "inline-flex"
        : "none";
    this.search.placeholder =
      this.activeTab === "prompts"
        ? "Search prompt names or text"
        : "Search tags or wildcard paths";
  }

  async loadTree() {
    this.updateTabUi();
    if (this.activeTab === "prompts") {
      await this.loadPromptTree();
      return;
    }

    this.details.innerHTML =
      "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view tags and preview.</div>";

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

    if (this.activeTab === "prompts") {
      const result = await searchPrompts({ query, limit: 120 });
      this.items = result.results ?? [];
      this.renderPromptResults();
      return;
    }

    const types = [...this.filterInputs.entries()]
      .filter(([_type, input]) => input.checked)
      .map(([type]) => type);
    if (!types.length) {
      this.results.innerHTML =
        "<div class='charlierz-wildcard-browser-empty'>Select at least one result type.</div>";
      return;
    }

    const url = new URL(
      "/charlierz-prompt-catalog/search",
      window.location.origin,
    );
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

  async loadPromptTree() {
    try {
      const result = await loadPrompts();
      this.items = [];
      this.results.innerHTML = "";
      this.renderTreeNode(result.tree, this.results, 0);
      this.renderPromptEditor();
    } catch (error) {
      this.results.innerHTML = `<div class='charlierz-wildcard-browser-empty'>${error.message || error}</div>`;
    }
  }

  renderPromptResults() {
    this.results.innerHTML = "";
    if (!this.items.length) {
      this.results.innerHTML =
        "<div class='charlierz-wildcard-browser-empty'>No prompts.</div>";
      return;
    }
    for (const [index, item] of this.items.entries()) {
      this.renderResultRow(item, index, this.results, { showPath: true });
    }
  }

  renderPromptEditor() {
    this.details.innerHTML = "";
    const appendSeparator = () => {
      const separator = document.createElement("div");
      separator.className = "charlierz-prompt-browser-section-separator";
      this.details.appendChild(separator);
    };

    const libraryHeader = this.promptLibraryActions.querySelector(
      ".charlierz-prompt-browser-action-header",
    );
    this.promptLibraryActions.insertBefore(
      this.promptIdInput,
      libraryHeader.nextSibling,
    );

    this.promptEditorActions.appendChild(this.decomposePromptLabel);

    this.details.appendChild(this.promptLibraryActions);
    appendSeparator();
    this.details.appendChild(this.promptEditorActions);
    this.details.appendChild(this.promptEditor);
    appendSeparator();
    this.details.appendChild(this.promptPreviewActions);
    this.details.appendChild(this.promptPreview);
  }

  getTargetText() {
    if (!this.node) return "";
    return isPromptHelperNode(this.node)
      ? getPromptHelperText(this.node)
      : String(getWidgetValue(this.node, "wildcard_text") ?? "").trim();
  }

  clearTarget({ confirmClear = true } = {}) {
    if (!this.node || !this.getTargetText()) return true;
    if (
      confirmClear &&
      !confirm("Clear current node prompt text? Unsaved node edits will be lost.")
    )
      return false;
    return isPromptHelperNode(this.node)
      ? clearPromptHelper(this.node)
      : setWidgetValue(this.node, "wildcard_text", "");
  }

  async insertPromptEditorIntoTarget({ replace = false } = {}) {
    if (!this.promptEditor.value.trim()) throw new Error("Prompt text is empty");
    if (replace && !this.clearTarget({ confirmClear: true })) return false;
    return isPromptHelperNode(this.node) && this.promptCategoriesValue
      ? appendPromptCategories(this.node, this.promptCategoriesValue)
      : isPromptHelperNode(this.node) && this.decomposePromptInput.checked
        ? appendDecomposedPrompt(
            this.node,
            await decomposePromptText(this.promptEditor.value),
            { focusedText: this.promptEditor.value },
          )
        : this.insertText(this.promptEditor.value, {
            mode: "block",
            forceFocused: true,
          });
  }

  getCurrentNodePromptPayload() {
    return isPromptHelperNode(this.node)
      ? {
          text: getPromptHelperText(this.node),
          categories: getPromptHelperCategories(this.node),
        }
      : {
          text: String(getWidgetValue(this.node, "wildcard_text") ?? ""),
          categories: null,
        };
  }

  async saveCurrentNodePrompt({ saveAs = false } = {}) {
    const payload = this.getCurrentNodePromptPayload();
    if (!payload.text.trim()) throw new Error("Current node prompt is empty");

    let id = saveAs ? "" : (this.promptSelected?.id ?? "");
    if (!id || saveAs) {
      const entered = prompt("Prompt id", id);
      if (!entered) return null;
      id = entered;
    } else if (!confirm(`Overwrite saved prompt ${id} with current node text?`)) {
      return null;
    }

    let saved;
    try {
      saved = await savePrompt({
        id,
        text: payload.text,
        categories: payload.categories,
        overwrite: !saveAs && this.promptSelected?.id === id,
      });
    } catch (error) {
      if (
        error.status !== 409 ||
        !confirm(`${error.message}\n\nOverwrite existing prompt?`)
      )
        throw error;
      saved = await savePrompt({
        id,
        text: payload.text,
        categories: payload.categories,
        overwrite: true,
      });
    }

    await this.loadPromptDetail(saved.id);
    await this.loadTree();
    return saved;
  }

  async runPromptAction(action, button) {
    if (action === "saveCurrent" || action === "saveCurrentAs") {
      const saved = await this.saveCurrentNodePrompt({
        saveAs: action === "saveCurrentAs",
      });
      if (saved) flashInserted(button);
      return;
    }

    if (action === "new") {
      if (!this.canDiscardPromptEdits()) return;
      this.promptSelected = null;
      this.selected = null;
      this.promptIdInput.value = "";
      this.promptEditor.value = "";
      this.promptLoadedText = "";
      this.promptDirty = false;
      this.promptCategoriesValue = null;
      this.promptPreview.textContent = "Preview output appears here.";
      this.promptEditor.focus();
      return;
    }

    if (action === "newCurrent") {
      if (!this.canDiscardPromptEdits()) return;
      this.promptSelected = null;
      this.selected = null;
      this.promptIdInput.value = "";
      this.promptCategoriesValue = isPromptHelperNode(this.node)
        ? getPromptHelperCategories(this.node)
        : null;
      this.promptEditor.value = isPromptHelperNode(this.node)
        ? getPromptHelperText(this.node)
        : getWidgetValue(this.node, "wildcard_text");
      this.promptLoadedText = "";
      this.promptDirty = true;
      this.promptEditor.focus();
      return;
    }

    if (action === "insert" || action === "replace") {
      const inserted = await this.insertPromptEditorIntoTarget({
        replace: action === "replace",
      });
      if (inserted) flashInserted(button);
      return;
    }

    if (action === "clear") {
      if (this.clearTarget({ confirmClear: true })) flashInserted(button);
      return;
    }

    if (action === "preview") {
      const response = await api.fetchApi("/charlierz-prompt-catalog/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: this.promptEditor.value,
          seed: Math.floor(Math.random() * 0xffffffff),
          weightMode: getWidgetValue(this.node, "weight_mode") || "sqrt",
        }),
      });
      const result = await response.json();
      if (!response.ok || result.error)
        throw new Error(
          result.error || `Preview failed with HTTP ${response.status}`,
        );
      const diagnostics = result.diagnostics?.length
        ? `\n\nDiagnostics:\n${result.diagnostics.join("\n")}`
        : "";
      this.promptPreview.textContent = `${result.processedText ?? ""}${diagnostics}`;
      return;
    }

    if (action === "delete") {
      const id = this.promptIdInput.value.trim();
      if (!id) throw new Error("Missing prompt id");
      if (!confirm(`Delete prompt ${id}?`)) return;
      await deletePrompt(id);
      this.promptSelected = null;
      this.selected = null;
      this.promptIdInput.value = "";
      this.promptEditor.value = "";
      this.promptLoadedText = "";
      this.promptDirty = false;
      this.promptCategoriesValue = null;
      await this.loadTree();
      return;
    }

    if (action === "rename") {
      const id = this.promptSelected?.id ?? this.promptIdInput.value.trim();
      if (!id) throw new Error("Missing prompt id");
      const newId = prompt("New prompt id", id);
      if (!newId) return;
      let renamed;
      try {
        renamed = await renamePrompt({ id, newId, overwrite: false });
      } catch (error) {
        if (
          error.status !== 409 ||
          !confirm(`${error.message}\n\nOverwrite existing prompt?`)
        )
          throw error;
        renamed = await renamePrompt({ id, newId, overwrite: true });
      }
      await this.loadPromptDetail(renamed.id);
      await this.loadTree();
      return;
    }

    if (action === "save") {
      const id = this.promptIdInput.value.trim();
      if (!id) throw new Error("Missing prompt id");
      const saved = await savePrompt({
        id,
        text: this.promptEditor.value,
        categories: this.promptCategoriesValue,
        overwrite: true,
      });
      await this.loadPromptDetail(saved.id);
      await this.loadTree();
    }
  }

  async loadPromptDetail(id) {
    const detail = await loadPromptDetail(id);
    this.promptSelected = detail;
    this.promptIdInput.value = detail.id;
    this.promptEditor.value = detail.text ?? "";
    this.promptLoadedText = this.promptEditor.value;
    this.promptDirty = false;
    this.promptCategoriesValue = detail.categories ?? null;
    this.promptPreview.textContent =
      detail.preview || "Preview output appears here.";
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
        summaryLabel.textContent = child.id
          ? formatWildcardLabel(child.label, child.tagCount)
          : child.label;
        summary.appendChild(summaryLabel);

        if (child.id && this.activeTab === "wildcards") {
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

        if (child.id && this.activeTab === "prompts") {
          const index = this.items.push(child) - 1;
          this.renderResultRow(child, index, parent, {
            className: "charlierz-wildcard-browser-tree-leaf",
            label: `${child.label} (prompt)`,
            paddingLeft: 8 + depth * 14,
          });
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
      this.results.innerHTML =
        "<div class='charlierz-wildcard-browser-empty'>No results.</div>";
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
    row.className =
      `charlierz-wildcard-browser-result ${options.className ?? ""}`.trim();
    row.dataset.resultIndex = `${index}`;
    if (typeof options.paddingLeft === "number")
      row.style.paddingLeft = `${options.paddingLeft}px`;
    if (item === this.selected) row.classList.add("selected");

    const content = document.createElement("div");
    content.className = "charlierz-wildcard-browser-result-content";

    const label = document.createElement("div");
    label.className = "charlierz-wildcard-browser-result-label";
    const defaultLabel =
      item.type === "wildcard" && item.tagCount
        ? formatWildcardLabel(item.label ?? item.id, item.tagCount)
        : (item.label ?? item.insertText ?? item.id);
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

    if (this.activeTab === "wildcards" && item.type === "wildcard") {
      const insert = document.createElement("button");
      insert.type = "button";
      insert.className = "charlierz-wildcard-browser-row-insert";
      insert.dataset.insertResult = "true";
      insert.dataset.resultIndex = `${index}`;
      insert.textContent = "Insert wildcard";
      insert.title = insert.textContent;
      row.appendChild(insert);
    }

    parent.appendChild(row);
  }

  async select(index) {
    this.selected = this.items[index] ?? null;
    if (this.activeTab === "prompts" && this.selected?.type === "prompt") {
      if (!this.canDiscardPromptEdits()) return;
      await this.loadPromptDetail(this.selected.id);
    }
    for (const row of this.results.querySelectorAll("[data-result-index]")) {
      row.classList.toggle(
        "selected",
        Number(row.dataset.resultIndex) === index,
      );
    }
    await this.renderDetails();
  }

  async renderDetails() {
    if (this.activeTab === "prompts") {
      this.renderPromptEditor();
      return;
    }

    this.details.innerHTML = "";
    if (!this.selected) {
      this.details.innerHTML =
        "<div class='charlierz-wildcard-browser-empty'>Select a wildcard to view tags and preview.</div>";
      return;
    }

    let detail = null;
    if (this.selected.type === "wildcard") {
      const url = new URL(
        "/charlierz-prompt-catalog/wildcard",
        window.location.origin,
      );
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
    const titleText =
      this.selected.label ?? this.selected.insertText ?? this.selected.id;
    title.textContent = detail
      ? formatWildcardLabel(titleText, detail.tagCount ?? detail.tags.length)
      : titleText;
    header.appendChild(title);

    const actions = document.createElement("div");
    actions.className = "charlierz-wildcard-browser-detail-actions";

    const insertButton = document.createElement("button");
    insertButton.type = "button";
    insertButton.dataset.insertSelected = "true";
    insertButton.textContent =
      this.selected.type === "wildcard"
        ? "Insert wildcard"
        : "Insert selected text";
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
      if (detail.metadata?.promptCategory) {
        row.dataset.promptCategory = detail.metadata.promptCategory;
      }
      row.title = "Insert tag";

      const text = document.createElement("span");
      text.textContent = formatTagWeight(tag.text, tag.weight);
      row.appendChild(text);
      tags.appendChild(row);
    }
    this.details.appendChild(tags);
  }

  async insertSelected({ close = true } = {}) {
    return this.insertItem(this.selected, { close });
  }

  insertText(
    text,
    { mode = "comma", category = null, forceFocused = false } = {},
  ) {
    if (!this.node) return false;
    if (isPromptHelperNode(this.node)) {
      return insertIntoPromptHelper(this.node, text, {
        mode,
        category,
        forceFocused,
      });
    }
    return insertIntoWidget(this.node, "wildcard_text", text, { mode });
  }

  async insertItem(item, { close = true } = {}) {
    if (!this.node || !item) return false;
    const text = item.insertText ?? item.label ?? "";
    const inserted =
      isPromptHelperNode(this.node) && item.type === "prompt" && item.categories
        ? appendPromptCategories(this.node, item.categories)
        : isPromptHelperNode(this.node) &&
            item.type === "prompt" &&
            this.decomposePromptInput.checked
          ? appendDecomposedPrompt(this.node, await decomposePromptText(text), {
              focusedText: text,
            })
          : this.insertText(text, {
              mode: item.type === "prompt" ? "block" : "comma",
              category: item.promptCategory ?? item.category ?? null,
              forceFocused: item.type === "prompt",
            });
    if (inserted && close) this.hide();
    return inserted;
  }
}

const wildcardBrowser = new WildcardBrowser();

function useLastQueuedWildcardSeed(node) {
  const lastSeed =
    node.lastWildcardSeed ?? node.properties?.[LAST_WILDCARD_SEED_PROPERTY];
  if (!Number.isFinite(Number(lastSeed))) {
    alert("No queued wildcard seed recorded yet. Run the node once first.");
    return;
  }
  setWidgetValue(node, "seed", Number(lastSeed));
  setWidgetValue(node, "control_after_generate", "fixed");
}

function rememberWildcardSeedOnExecuted(nodeType) {
  const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    originalOnNodeCreated?.apply(this, arguments);
    const lastSeed = this.properties?.[LAST_WILDCARD_SEED_PROPERTY];
    if (Number.isFinite(Number(lastSeed))) {
      this.lastWildcardSeed = Number(lastSeed);
    }
  };

  const originalOnExecuted = nodeType.prototype.onExecuted;
  nodeType.prototype.onExecuted = function (message) {
    originalOnExecuted?.apply(this, arguments);
    const lastSeed = getFirstUiValue(message, "last_seed");
    if (Number.isFinite(Number(lastSeed))) {
      this.lastWildcardSeed = Number(lastSeed);
      setNodeProperty(this, LAST_WILDCARD_SEED_PROPERTY, Number(lastSeed));
    }
  };
}

function restorePreviewAnyText(node) {
  const previewText = node.properties?.[LAST_PREVIEW_TEXT_PROPERTY];
  if (typeof previewText !== "string") return false;

  let restored = false;
  for (const name of ["preview_text", "preview_markdown"]) {
    restored = setWidgetValue(node, name, previewText) || restored;
  }

  for (const widget of node.widgets ?? []) {
    if (
      !String(widget.name ?? "")
        .toLowerCase()
        .includes("preview")
    )
      continue;
    widget.value = previewText;
    widget.callback?.(previewText);
    restored = true;
  }

  if (restored) node.setDirtyCanvas?.(true, true);
  return restored;
}

function rememberPreviewAnyText(nodeType) {
  const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    originalOnNodeCreated?.apply(this, arguments);
    restorePreviewAnyText(this);
    setTimeout(() => restorePreviewAnyText(this), 0);
  };

  const originalOnExecuted = nodeType.prototype.onExecuted;
  nodeType.prototype.onExecuted = function (message) {
    originalOnExecuted?.apply(this, arguments);
    const previewText = getFirstUiValue(message, "text");
    if (typeof previewText === "string") {
      setNodeProperty(this, LAST_PREVIEW_TEXT_PROPERTY, previewText);
      restorePreviewAnyText(this);
    }
  };
}

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
    if (nodeData.name === "PreviewAny") {
      rememberPreviewAnyText(nodeType);
      return;
    }

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

    if (nodeData.name === "PromptHelper") {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        addActionButton(this, "Prompt Catalog", () => {
          wildcardBrowser.show(this);
        });
      };
      return;
    }

    if (nodeData.name === "PromptFreeze") {
      const originalOnExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (message) {
        originalOnExecuted?.apply(this, arguments);
        const captured = message?.captured_text?.[0];
        if (typeof captured === "string") {
          setWidgetValue(this, "frozen_text", captured);
        }
      };
      return;
    }

    if (nodeData.name === "WildcardExpander") {
      rememberWildcardSeedOnExecuted(nodeType);
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        addActionButton(this, "Use Last Queued Seed", () => {
          useLastQueuedWildcardSeed(this);
        });
      };
      return;
    }

    if (nodeData.name === "WildcardProcessor") {
      rememberWildcardSeedOnExecuted(nodeType);
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        addActionButton(this, "Prompt Catalog", () => {
          wildcardBrowser.show(this);
        });
        addActionButton(this, "Use Last Queued Seed", () => {
          useLastQueuedWildcardSeed(this);
        });
        addActionButton(this, "Preview / Reroll", async () => {
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
      addActionButton(this, "Reload Models", async () => {
        try {
          await reloadLlamaCppModels(this);
        } catch (error) {
          console.error(error);
          alert(error.message || String(error));
        }
      });
      addActionButton(this, "Unload Model", async () => {
        try {
          await unloadLlamaCppModel(this);
        } catch (error) {
          console.error(error);
          alert(error.message || String(error));
        }
      });
    };
  },

  async setup() {
    loadCss();

    try {
      const config = await loadPromptCategories();
      promptCategories = config.categories ?? [];
      promptCategoryIds = new Set(
        promptCategories.map((category) => category.id),
      );
      promptCategorySourceMap = new Map(
        promptCategories.map((category) => [
          category.id,
          category.sources ?? [],
        ]),
      );
      autocomplete.setPromptCategories(promptCategories);
    } catch (error) {
      console.error("[PromptHelper] Failed to load prompt categories", error);
    }

    const originalStringWidget = ComfyWidgets.STRING;
    ComfyWidgets.STRING = function (node, inputName, inputData, appInstance) {
      const result = originalStringWidget.apply(this, arguments);

      const element = result?.widget?.element ?? result?.widget?.inputEl;
      if (!isAutocompleteElement(element)) return result;

      if (isPromptHelperWidget(node, inputName)) {
        const prioritySources = [
          { source: inputName, className: "category-priority-match" },
        ];
        if (hasPromptCategorySource(inputName, "tag_entities/characters")) {
          prioritySources.unshift({
            source: "characters",
            className: "character-priority-match",
          });
        }
        if (hasPromptCategorySource(inputName, "tag_entities/franchises")) {
          prioritySources.unshift({
            source: "copyrights",
            className: "copyright-priority-match",
          });
        }

        element.addEventListener("focus", () => {
          promptHelperFocusedCategory.set(node, inputName);
        });
        autocomplete.attach(element, "general", {
          enableRelatedTags: true,
          relatedCategory: inputName,
          prioritySources,
          node,
          categoryName: inputName,
          searchContext: "wildcard",
          searchTypes: ["wildcard", "tag"],
        });
        attachWildcardProcessorPreview(element);
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
