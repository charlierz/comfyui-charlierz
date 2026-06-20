const relatedCache = new Map();
const characterTagCache = new Map();
let relatedMethodsCache = null;
let promptCategoriesCache = null;

export async function loadPromptCategories() {
  if (promptCategoriesCache) return promptCategoriesCache;

  const response = await fetch("/charlierz-prompt-helper/categories", {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load prompt categories: ${response.status}`);
  }

  promptCategoriesCache = await response.json();
  return promptCategoriesCache;
}

export async function loadRelatedMethods() {
  if (relatedMethodsCache) return relatedMethodsCache;

  const response = await fetch("/charlierz-prompt-helper/related-methods", {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load related tag methods: ${response.status}`);
  }

  relatedMethodsCache = await response.json();
  return relatedMethodsCache;
}

export async function loadCharacterTags(character) {
  if (characterTagCache.has(character)) return characterTagCache.get(character);

  const url = new URL(
    "/charlierz-prompt-helper/character-tags",
    window.location.origin,
  );
  url.searchParams.set("character", character);

  const response = await fetch(url, { cache: "no-store" });
  if (response.status === 404) {
    characterTagCache.set(character, null);
    return null;
  }
  if (!response.ok) {
    throw new Error(
      `Failed to load character tags for ${character}: ${response.status}`,
    );
  }

  const tags = await response.json();
  characterTagCache.set(character, tags);
  return tags;
}

export async function decomposePromptText(text) {
  const response = await fetch("/charlierz-prompt-helper/decompose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      result.error || `Failed to decompose prompt: ${response.status}`,
    );
  }
  return result;
}

export async function loadPrompts() {
  const response = await fetch("/charlierz-prompt-catalog/prompts", {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to load prompts: ${response.status}`);
  }
  return response.json();
}

export async function loadPromptDetail(id) {
  const url = new URL(
    "/charlierz-prompt-catalog/prompt",
    window.location.origin,
  );
  url.searchParams.set("id", id);

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load prompt ${id}: ${response.status}`);
  }

  return response.json();
}

export async function searchPrompts({ query, limit = 80 }) {
  const url = new URL(
    "/charlierz-prompt-catalog/prompt-search",
    window.location.origin,
  );
  url.searchParams.set("q", query);
  url.searchParams.set("limit", `${limit}`);

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to search prompts: ${response.status}`);
  }

  return response.json();
}

export async function savePrompt({ id, text, overwrite = false }) {
  const response = await fetch("/charlierz-prompt-catalog/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, text, overwrite }),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(
      result.error || `Failed to save prompt: ${response.status}`,
    );
    error.status = response.status;
    throw error;
  }
  return result;
}

export async function renamePrompt({ id, newId, overwrite = false }) {
  const response = await fetch("/charlierz-prompt-catalog/prompt/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, newId, overwrite }),
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(
      result.error || `Failed to rename prompt: ${response.status}`,
    );
    error.status = response.status;
    throw error;
  }
  return result;
}

export async function deletePrompt(id) {
  const response = await fetch("/charlierz-prompt-catalog/prompt/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      result.error || `Failed to delete prompt: ${response.status}`,
    );
  }
  return result;
}

export async function loadWildcardDetail(id) {
  const url = new URL(
    "/charlierz-prompt-catalog/wildcard",
    window.location.origin,
  );
  url.searchParams.set("id", id);

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load wildcard ${id}: ${response.status}`);
  }

  return response.json();
}

export async function searchCatalog({
  query,
  context = "prompt",
  category = null,
  types = null,
  limit = 80,
}) {
  const url = new URL(
    "/charlierz-prompt-catalog/search",
    window.location.origin,
  );
  url.searchParams.set("q", query);
  url.searchParams.set("context", context);
  url.searchParams.set("limit", `${limit}`);
  if (category) url.searchParams.set("category", category);
  if (types?.length) url.searchParams.set("types", types.join(","));

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to search prompt catalog: ${response.status}`);
  }

  return response.json();
}

export async function loadRelatedTags(method, category, tag) {
  const key = `${method}:${category}:${tag}`;
  if (relatedCache.has(key)) return relatedCache.get(key);

  const url = new URL(
    `/charlierz-prompt-helper/related/${encodeURIComponent(method)}/${encodeURIComponent(category)}`,
    window.location.origin,
  );
  url.searchParams.set("tag", tag);

  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(
      `Failed to load related tags for ${method}/${category}/${tag}: ${response.status}`,
    );
  }

  const detail = await response.json();
  relatedCache.set(key, detail);
  return detail;
}
