import {
  CATEGORY_INPUTS,
  loadCharacterTags,
  loadRelatedMethods,
  loadRelatedTags,
  loadTags,
} from "./data.js";
import {
  getCurrentPartialTag,
  getCurrentTagRange,
  getExistingTags,
  insertText,
  normalizeTag,
  positionBelowElement,
} from "./utils.js";

const MAX_AUTOCOMPLETE_RESULTS = 80;
const MAX_RELATED_RESULTS = 80;
const RELATED_METHOD_STORAGE_KEY = "charlierz.promptHelper.relatedMethod";
const DEFAULT_RELATED_METHOD = "jaccard";
const CATEGORY_DISPLAY_NAMES = {
  style_quality: "Style / Quality",
  themes_roles: "Themes / Roles",
  appearance_anatomy: "Appearance / Anatomy",
  clothing_accessories: "Clothing / Accessories",
  actions_poses: "Actions / Poses",
  expressions: "Expressions",
  scene_background: "Scene / Background",
};
const CHARACTER_POPUP_CATEGORY_ORDER = [
  "appearance_anatomy",
  "clothing_accessories",
  ...CATEGORY_INPUTS.filter(
    (category) =>
      !["appearance_anatomy", "clothing_accessories"].includes(category),
  ),
];

function openDanbooruWiki(tag) {
  window.open(
    `https://danbooru.donmai.us/wiki_pages/${encodeURIComponent(tag)}`,
    "_blank",
    "noopener,noreferrer",
  );
}

function getTagValue(item) {
  return typeof item === "string" ? item : item.tag;
}

function searchTags(tags, query, priorityTagClasses = null) {
  const normalizedQuery = normalizeTag(query).toLowerCase();
  if (!normalizedQuery) return [];

  const matches = [];
  const seenTags = new Set();

  for (const tag of tags) {
    const normalizedTag = tag.toLowerCase();
    if (seenTags.has(normalizedTag) || !normalizedTag.includes(normalizedQuery)) {
      continue;
    }

    seenTags.add(normalizedTag);
    matches.push({
      tag,
      priorityClass: priorityTagClasses?.get(normalizedTag) ?? null,
    });

    if (matches.length >= MAX_AUTOCOMPLETE_RESULTS) break;
  }

  return matches;
}

function appendTags(textarea, tags) {
  const existingTags = new Set(getExistingTags(textarea));
  const tagsToInsert = tags.filter((tag) => !existingTags.has(normalizeTag(tag)));
  if (!tagsToInsert.length) return;

  const trimmedValue = textarea.value.trimEnd();
  const prefix = trimmedValue ? (trimmedValue.endsWith(",") ? " " : ", ") : "";
  const start = textarea.value.length;
  insertText(textarea, start, start, `${prefix}${tagsToInsert.join(", ")}`);
}

class CharacterTagsPopup {
  constructor() {
    this.root = document.createElement("div");
    this.root.id = "charlierz-prompt-helper-character-tags";
    this.root.className = "charlierz-tag-popup charlierz-character-tags-popup";
    this.root.style.display = "none";

    this.header = document.createElement("div");
    this.header.className = "charlierz-tag-popup-title";
    this.title = document.createElement("span");
    this.header.appendChild(this.title);
    this.root.appendChild(this.header);

    this.content = document.createElement("div");
    this.content.className = "charlierz-character-tags-content";
    this.root.appendChild(this.content);

    document.body.appendChild(this.root);
    this.onAdd = null;
    this.currentCategories = null;

    this.root.addEventListener("mousedown", (event) => {
      const danbooruLink = event.target.closest(".charlierz-danbooru-link");
      if (danbooruLink) {
        event.preventDefault();
        event.stopPropagation();
        openDanbooruWiki(danbooruLink.dataset.tag);
        return;
      }

      const addButton = event.target.closest("[data-character-add-category]");
      if (addButton) {
        event.preventDefault();
        event.stopPropagation();
        this.onAdd?.(addButton.dataset.characterAddCategory, null);
        this.hide();
        return;
      }

      const tagItem = event.target.closest("[data-character-tag]");
      if (tagItem) {
        event.preventDefault();
        event.stopPropagation();
        this.onAdd?.(tagItem.dataset.characterCategory, [tagItem.dataset.characterTag]);
        tagItem.classList.add("already-used");
        return;
      }
    });
  }

  isVisible() {
    return this.root.style.display !== "none";
  }

  show(target, characterData, nodeTextareas, onAdd) {
    this.onAdd = onAdd;
    this.currentCategories = characterData.categories ?? {};
    this.title.innerHTML = "";
    this.title.appendChild(document.createTextNode(`Character tags: ${characterData.character}`));

    const danbooruLink = document.createElement("span");
    danbooruLink.className = "charlierz-danbooru-link header-link";
    danbooruLink.dataset.tag = characterData.character;
    danbooruLink.title = "Open Danbooru wiki page";
    danbooruLink.textContent = "↗";
    this.title.appendChild(danbooruLink);

    this.content.innerHTML = "";
    for (const category of CHARACTER_POPUP_CATEGORY_ORDER) {
      const tags = characterData.categories?.[category] ?? [];
      const textarea = nodeTextareas?.get(category);
      if (!tags.length || !textarea) continue;

      const group = document.createElement("div");
      group.className = "charlierz-character-tags-group";

      const groupHeader = document.createElement("div");
      groupHeader.className = "charlierz-character-tags-group-header";
      groupHeader.textContent = CATEGORY_DISPLAY_NAMES[category] ?? category;

      const addButton = document.createElement("button");
      addButton.type = "button";
      addButton.dataset.characterAddCategory = category;
      addButton.textContent = `Add ${tags.length}`;
      groupHeader.appendChild(addButton);
      group.appendChild(groupHeader);

      const existingSet = new Set(getExistingTags(textarea));
      for (const tag of tags) {
        const item = document.createElement("div");
        item.className = "charlierz-tag-popup-item";
        item.dataset.characterCategory = category;
        item.dataset.characterTag = tag;
        if (existingSet.has(normalizeTag(tag))) item.classList.add("already-used");

        const tagName = document.createElement("span");
        tagName.className = "charlierz-tag-name";
        tagName.textContent = tag;
        item.appendChild(tagName);

        const link = document.createElement("span");
        link.className = "charlierz-danbooru-link";
        link.dataset.tag = tag;
        link.title = "Open Danbooru wiki page";
        link.textContent = "↗";
        item.appendChild(link);
        group.appendChild(item);
      }

      this.content.appendChild(group);
    }

    positionBelowElement(this.root, target);
    this.root.style.display = "block";
  }

  hide() {
    this.root.style.display = "none";
    this.onAdd = null;
    this.currentCategories = null;
  }
}

class TagPopup {
  constructor(id, title) {
    this.root = document.createElement("div");
    this.root.id = id;
    this.root.className = "charlierz-tag-popup";
    this.root.style.display = "none";

    this.header = document.createElement("div");
    this.header.className = "charlierz-tag-popup-title";

    this.title = document.createElement("span");
    this.title.textContent = title;
    this.header.appendChild(this.title);

    this.root.appendChild(this.header);

    this.header.addEventListener("mousedown", (event) => {
      const danbooruLink = event.target.closest(".charlierz-danbooru-link");
      if (!danbooruLink) return;

      event.preventDefault();
      event.stopPropagation();
      openDanbooruWiki(danbooruLink.dataset.tag);
    });

    this.list = document.createElement("div");
    this.list.className = "charlierz-tag-popup-list";
    this.root.appendChild(this.list);

    document.body.appendChild(this.root);

    this.items = [];
    this.selectedIndex = 0;
    this.onSelect = null;

    this.list.addEventListener("mousedown", (event) => {
      const danbooruLink = event.target.closest(".charlierz-danbooru-link");
      if (danbooruLink) {
        event.preventDefault();
        event.stopPropagation();
        openDanbooruWiki(danbooruLink.dataset.tag);
        return;
      }

      const item = event.target.closest(".charlierz-tag-popup-item");
      if (!item) return;

      event.preventDefault();
      event.stopPropagation();
      this.onSelect?.(item.dataset.tag);
    });
  }

  isVisible() {
    return this.root.style.display !== "none";
  }

  setHeaderControl(control) {
    this.header.appendChild(control);
  }

  show(target, title, tags, existingTags, onSelect, titleLinkTag = null) {
    this.items = tags;
    this.selectedIndex = 0;
    this.onSelect = onSelect;
    this.title.innerHTML = "";
    this.title.appendChild(document.createTextNode(title));
    if (titleLinkTag) {
      const danbooruLink = document.createElement("span");
      danbooruLink.className = "charlierz-danbooru-link header-link";
      danbooruLink.dataset.tag = titleLinkTag;
      danbooruLink.title = "Open Danbooru wiki page";
      danbooruLink.textContent = "↗";
      this.title.appendChild(danbooruLink);
    }
    this.list.innerHTML = "";

    const existingSet = new Set(existingTags);
    for (const [index, tagItem] of tags.entries()) {
      const tag = getTagValue(tagItem);
      const item = document.createElement("div");
      item.className = "charlierz-tag-popup-item";
      item.dataset.index = `${index}`;
      item.dataset.tag = tag;
      if (tagItem?.priorityClass) {
        item.classList.add("priority-match", tagItem.priorityClass);
      }

      const tagName = document.createElement("span");
      tagName.className = "charlierz-tag-name";
      tagName.textContent = tag;
      item.appendChild(tagName);

      const danbooruLink = document.createElement("span");
      danbooruLink.className = "charlierz-danbooru-link";
      danbooruLink.dataset.tag = tag;
      danbooruLink.title = "Open Danbooru wiki page";
      danbooruLink.textContent = "↗";
      item.appendChild(danbooruLink);

      if (existingSet.has(normalizeTag(tag))) {
        item.classList.add("already-used");
      }
      this.list.appendChild(item);
    }

    positionBelowElement(this.root, target);
    this.root.style.display = "block";
    this.#highlightSelected();
  }

  hide() {
    this.root.style.display = "none";
    this.items = [];
    this.selectedIndex = 0;
    this.onSelect = null;
  }

  navigate(direction) {
    if (!this.items.length) return;
    this.selectedIndex += direction;
    if (this.selectedIndex < 0) this.selectedIndex = this.items.length - 1;
    if (this.selectedIndex >= this.items.length) this.selectedIndex = 0;
    this.#highlightSelected();
  }

  selectCurrent() {
    const tag = getTagValue(this.items[this.selectedIndex]);
    if (tag) this.onSelect?.(tag);
  }

  #highlightSelected() {
    [...this.list.children].forEach((item, index) => {
      item.classList.toggle("selected", index === this.selectedIndex);
      if (index === this.selectedIndex) item.scrollIntoView({ block: "nearest" });
    });
  }
}

export class PromptHelperAutocomplete {
  constructor() {
    this.autocompletePopup = new TagPopup(
      "charlierz-prompt-helper-autocomplete",
      "Tags",
    );
    this.relatedPopup = new TagPopup(
      "charlierz-prompt-helper-related",
      "Related tags",
    );
    this.characterTagsPopup = new CharacterTagsPopup();
    this.textareaConfig = new WeakMap();
    this.nodeTextareas = new WeakMap();
    this.attachedTextareas = new WeakSet();
    this.relatedMethods = [];
    this.relatedMethod =
      localStorage.getItem(RELATED_METHOD_STORAGE_KEY) ?? DEFAULT_RELATED_METHOD;
    this.currentRelatedRequest = null;
    this.#initializeRelatedMethodSelector();
    document.addEventListener("keydown", (event) => this.#handleDocumentKeyDown(event));
    document.addEventListener("pointerdown", (event) => this.#handleDocumentPointerDown(event), true);
  }

  #hideAllPopups() {
    this.currentRelatedRequest = null;
    this.autocompletePopup.hide();
    this.relatedPopup.hide();
    this.characterTagsPopup.hide();
  }

  #isPopupElement(element) {
    return (
      this.autocompletePopup.root.contains(element) ||
      this.relatedPopup.root.contains(element) ||
      this.characterTagsPopup.root.contains(element)
    );
  }

  #hasVisiblePopup() {
    return (
      this.autocompletePopup.isVisible() ||
      this.relatedPopup.isVisible() ||
      this.characterTagsPopup.isVisible()
    );
  }

  #handleDocumentKeyDown(event) {
    if (event.key !== "Escape" || !this.#hasVisiblePopup()) return;

    event.preventDefault();
    this.#hideAllPopups();
  }

  #handleDocumentPointerDown(event) {
    if (!this.#hasVisiblePopup()) return;

    const target = event.target;
    if (this.#isPopupElement(target) || this.textareaConfig.has(target)) return;

    this.#hideAllPopups();
  }

  async #initializeRelatedMethodSelector() {
    try {
      this.relatedMethods = await loadRelatedMethods();
      if (!this.relatedMethods.length) return;

      if (!this.relatedMethods.includes(this.relatedMethod)) {
        this.relatedMethod = this.relatedMethods.includes(DEFAULT_RELATED_METHOD)
          ? DEFAULT_RELATED_METHOD
          : this.relatedMethods[0];
        localStorage.setItem(RELATED_METHOD_STORAGE_KEY, this.relatedMethod);
      }

      const select = document.createElement("select");
      select.className = "charlierz-related-method-select";
      select.title = "Related tag calculation";

      for (const method of this.relatedMethods) {
        const option = document.createElement("option");
        option.value = method;
        option.textContent = method;
        option.selected = method === this.relatedMethod;
        select.appendChild(option);
      }

      select.addEventListener("mousedown", (event) => event.stopPropagation());
      select.addEventListener("keydown", (event) => event.stopPropagation());
      select.addEventListener("change", () => {
        this.relatedMethod = select.value;
        localStorage.setItem(RELATED_METHOD_STORAGE_KEY, this.relatedMethod);
        if (this.currentRelatedRequest) {
          this.#showRelatedTags(this.currentRelatedRequest);
        }
      });

      this.relatedPopup.setHeaderControl(select);
    } catch (error) {
      console.error("[PromptHelper] Failed to initialize related tag methods", error);
    }
  }

  attach(
    textarea,
    source,
    {
      enableRelatedTags = false,
      relatedCategory = source,
      prioritySources = [],
      node = null,
      categoryName = null,
    } = {},
  ) {
    if (this.attachedTextareas.has(textarea)) return;

    this.textareaConfig.set(textarea, {
      source,
      enableRelatedTags,
      relatedCategory,
      prioritySources,
      node,
      categoryName,
    });
    if (node && categoryName) {
      if (!this.nodeTextareas.has(node)) this.nodeTextareas.set(node, new Map());
      this.nodeTextareas.get(node).set(categoryName, textarea);
    }
    this.attachedTextareas.add(textarea);

    textarea.addEventListener("input", (event) => this.#handleInput(event));
    textarea.addEventListener("keyup", (event) => this.#handleKeyUp(event));
    textarea.addEventListener("keydown", (event) => this.#handleKeyDown(event));
    textarea.addEventListener("click", (event) => this.#handleClick(event));
    textarea.addEventListener("blur", (event) => this.#handleBlur(event));
  }

  async #handleInput(event) {
    const partial = getCurrentPartialTag(event.target);
    if (!partial) this.autocompletePopup.hide();
  }

  async #handleKeyUp(event) {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key.length > 1 && !["Backspace", "Delete"].includes(event.key)) return;

    const textarea = event.target;
    const config = this.textareaConfig.get(textarea);
    const partial = getCurrentPartialTag(textarea);
    if (!config || !partial) {
      this.autocompletePopup.hide();
      return;
    }

    const [sourceTags, ...priorityTagLists] = await Promise.all([
      loadTags(config.source),
      ...config.prioritySources.map(({ source }) => loadTags(source)),
    ]);

    const priorityTagClasses = new Map();
    for (const [index, tags] of priorityTagLists.entries()) {
      const priorityClass = config.prioritySources[index].className;
      for (const tag of tags) {
        const normalizedTag = tag.toLowerCase();
        if (!priorityTagClasses.has(normalizedTag)) {
          priorityTagClasses.set(normalizedTag, priorityClass);
        }
      }
    }

    const tags = [...new Set([...priorityTagLists.flat(), ...sourceTags])];
    const matches = searchTags(tags, partial, priorityTagClasses);
    if (!matches.length) {
      this.autocompletePopup.hide();
      return;
    }

    this.relatedPopup.hide();
    this.autocompletePopup.show(
      textarea,
      config.source.replaceAll("_", " "),
      matches,
      getExistingTags(textarea),
      (tag) => this.#insertAutocompleteTag(textarea, tag),
    );
  }

  #handleKeyDown(event) {
    const visiblePopup = this.autocompletePopup.isVisible()
      ? this.autocompletePopup
      : this.relatedPopup.isVisible()
        ? this.relatedPopup
        : this.characterTagsPopup.isVisible()
          ? this.characterTagsPopup
          : null;

    if (!visiblePopup) return;

    switch (event.key) {
      case "ArrowDown":
        if (!visiblePopup.navigate) return;
        event.preventDefault();
        visiblePopup.navigate(1);
        break;
      case "ArrowUp":
        if (!visiblePopup.navigate) return;
        event.preventDefault();
        visiblePopup.navigate(-1);
        break;
      case "Enter":
      case "Tab":
        if (
          visiblePopup.selectCurrent &&
          !event.shiftKey &&
          !event.ctrlKey &&
          !event.metaKey &&
          !event.altKey
        ) {
          event.preventDefault();
          visiblePopup.selectCurrent();
        }
        break;
      case "Escape":
        event.preventDefault();
        visiblePopup.hide();
        break;
    }
  }

  async #handleClick(event) {
    const textarea = event.target;
    const config = this.textareaConfig.get(textarea);
    if (!config?.enableRelatedTags) return;

    const range = getCurrentTagRange(textarea.value, textarea.selectionStart);
    const tag = normalizeTag(range?.tag);
    if (!tag) {
      this.currentRelatedRequest = null;
      this.relatedPopup.hide();
      return;
    }

    if (config.relatedCategory === "themes_roles") {
      const characterTags = await loadCharacterTags(tag);
      if (characterTags) {
        this.autocompletePopup.hide();
        this.relatedPopup.hide();
        this.characterTagsPopup.show(
          textarea,
          characterTags,
          this.nodeTextareas.get(config.node),
          (category, tags) => this.#insertCharacterTags(config.node, category, tags),
        );
        return;
      }
    }

    this.characterTagsPopup.hide();
    await this.#showRelatedTags({ textarea, category: config.relatedCategory, tag });
  }

  async #showRelatedTags(request) {
    this.currentRelatedRequest = request;
    const { textarea, category, tag } = request;

    const relatedTags = (
      await loadRelatedTags(this.relatedMethod, category, tag)
    ).slice(0, MAX_RELATED_RESULTS);
    if (!relatedTags.length) {
      this.relatedPopup.hide();
      return;
    }

    this.autocompletePopup.hide();
    this.characterTagsPopup.hide();
    this.relatedPopup.show(
      textarea,
      `Related to ${tag}`,
      relatedTags,
      getExistingTags(textarea),
      (relatedTag) => this.#insertRelatedTag(textarea, relatedTag),
      tag,
    );
  }

  #handleBlur(event) {
    const blurredTextarea = event.target;
    setTimeout(() => {
      if (this.currentRelatedRequest?.textarea !== blurredTextarea) return;

      if (
        !this.autocompletePopup.root.contains(document.activeElement) &&
        !this.relatedPopup.root.contains(document.activeElement) &&
        !this.characterTagsPopup.root.contains(document.activeElement)
      ) {
        this.currentRelatedRequest = null;
        this.autocompletePopup.hide();
        this.relatedPopup.hide();
        this.characterTagsPopup.hide();
      }
    }, 150);
  }

  #insertAutocompleteTag(textarea, tag) {
    const range = getCurrentTagRange(textarea.value, textarea.selectionStart);
    if (!range) return;

    const suffix = textarea.value[range.end] === "," ? "" : ", ";
    insertText(textarea, range.start, textarea.selectionStart, `${tag}${suffix}`);
    this.autocompletePopup.hide();
  }

  #insertRelatedTag(textarea, tag) {
    const range = getCurrentTagRange(textarea.value, textarea.selectionStart);
    const insertAt = range?.end ?? textarea.selectionStart;
    const prefix = textarea.value.slice(0, insertAt).trimEnd().endsWith(",")
      ? " "
      : ", ";

    insertText(textarea, insertAt, insertAt, `${prefix}${tag}`);
    this.currentRelatedRequest = null;
    this.relatedPopup.hide();
  }

  #insertCharacterTags(node, category, tags) {
    const nodeTextareas = this.nodeTextareas.get(node);
    const textarea = nodeTextareas?.get(category);
    if (!textarea) return;

    const characterTags = tags ?? this.characterTagsPopup.currentCategories?.[category] ?? [];
    appendTags(textarea, characterTags);
  }
}
