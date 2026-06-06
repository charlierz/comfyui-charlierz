function stripPromptWeight(tag) {
  const weightedGroup = tag.match(/^\((.*):[0-9]+(?:\.[0-9]+)?\)$/);
  if (weightedGroup) return weightedGroup[1];

  return tag.replace(/:[0-9]+(?:\.[0-9]+)?$/, "");
}

export function normalizeTag(tag) {
  return stripPromptWeight((tag ?? "").trim()).trim().replace(/ /g, "_");
}

export function getCurrentTagRange(text, cursorPos) {
  const startSeparator = Math.max(
    text.lastIndexOf(",", cursorPos - 1),
    text.lastIndexOf("\n", cursorPos - 1),
  );
  const start = startSeparator === -1 ? 0 : startSeparator + 1;

  let endComma = text.indexOf(",", cursorPos);
  let endNewline = text.indexOf("\n", cursorPos);
  if (endComma === -1) endComma = text.length;
  if (endNewline === -1) endNewline = text.length;
  const end = Math.min(endComma, endNewline);

  const rawTag = text.slice(start, end);
  const leadingWhitespace = rawTag.match(/^\s*/)?.[0].length ?? 0;
  const trailingWhitespace = rawTag.match(/\s*$/)?.[0].length ?? 0;
  const adjustedStart = start + leadingWhitespace;
  const adjustedEnd = end - trailingWhitespace;

  if (adjustedStart > cursorPos || adjustedEnd < cursorPos) return null;

  return {
    start: adjustedStart,
    end: adjustedEnd,
    tag: text.slice(adjustedStart, adjustedEnd),
  };
}

export function getCurrentPartialTag(textarea) {
  const range = getCurrentTagRange(textarea.value, textarea.selectionStart);
  if (!range || textarea.selectionStart <= range.start) return "";
  return normalizeTag(textarea.value.slice(range.start, textarea.selectionStart));
}

export function insertText(textarea, start, end, text) {
  textarea.focus();
  textarea.setSelectionRange(start, end);

  const inserted = document.execCommand("insertText", false, text);
  if (!inserted) {
    textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
    const cursorPos = start + text.length;
    textarea.setSelectionRange(cursorPos, cursorPos);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

export function getExistingTags(textarea) {
  return textarea.value
    .split(/[\n,]/)
    .map(normalizeTag)
    .filter(Boolean);
}

export function positionBelowElement(root, target) {
  const rect = target.getBoundingClientRect();
  const margin = 8;

  root.style.visibility = "hidden";
  root.style.display = "block";
  root.style.maxHeight = "";
  root.style.maxWidth = "";

  const rootRect = root.getBoundingClientRect();
  const left = Math.min(
    Math.max(rect.left, margin),
    window.innerWidth - rootRect.width - margin,
  );

  const spaceBelow = window.innerHeight - rect.bottom - margin;
  const spaceAbove = rect.top - margin;
  let top = rect.bottom;
  let maxHeight = spaceBelow;

  if (spaceBelow < Math.min(rootRect.height, 200) && spaceAbove > spaceBelow) {
    maxHeight = spaceAbove;
    top = Math.max(margin, rect.top - Math.min(rootRect.height, maxHeight));
  }

  root.style.left = `${left}px`;
  root.style.top = `${top}px`;
  root.style.maxHeight = `${Math.max(120, maxHeight)}px`;
  root.style.maxWidth = `${Math.min(520, window.innerWidth - margin * 2)}px`;
  root.style.display = "none";
  root.style.visibility = "visible";
}
