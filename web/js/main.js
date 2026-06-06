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
  return node?.comfyClass === "PromptHelper" && CATEGORY_INPUTS.includes(inputName);
}

function isAutocompleteElement(element) {
  return (
    element &&
    !element.readOnly &&
    (element.tagName === "TEXTAREA" ||
      (element.tagName === "INPUT" && ["", "text", "search"].includes(element.type)))
  );
}

function getWidgetValue(node, name) {
  return node.widgets?.find((widget) => widget.name === name)?.value ?? "";
}

function addReadOnlyTextWidget(node, name) {
  const result = ComfyWidgets.STRING(node, name, ["STRING", { multiline: true }], app);
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

async function reloadLlamaCppModels(node) {
  const modelsIniPath = String(getWidgetValue(node, "models_ini_path") || "").trim();
  if (!modelsIniPath) {
    alert("Missing models.ini path");
    return;
  }

  const params = new URLSearchParams({ path: modelsIniPath });
  if (node.comfyClass === "LlamaCppVisionChat") {
    params.set("vision_only", "true");
    params.set(
      "server_url",
      getWidgetValue(node, "server_url") || "http://127.0.0.1:8080",
    );
  }

  const response = await api.fetchApi(
    `/charlierz-llama-cpp/models-ini?${params.toString()}`,
  );
  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(result.error || `Model reload failed with HTTP ${response.status}`);
  }

  const modelWidget = node.widgets?.find((widget) => widget.name === "model");
  if (!modelWidget) {
    throw new Error("Model widget not found");
  }
  setComboWidgetValues(modelWidget, result.models ?? []);
  node.setDirtyCanvas(true, true);
}

async function unloadLlamaCppModel(node) {
  const serverUrl = getWidgetValue(node, "server_url") || "http://127.0.0.1:8080";
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
    throw new Error(result.error || `Unload failed with HTTP ${response.status}`);
  }
}


app.registerExtension({
  name: extensionId,
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "EstimateTextTokens") {
      const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        originalOnNodeCreated?.apply(this, arguments);
        this.tokenEstimateWidget = addReadOnlyTextWidget(this, "token_estimate");
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
      } else {
        autocomplete.attach(element, "general");
      }

      return result;
    };
  },
});
