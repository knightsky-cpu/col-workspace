export function setText(element, value) {
  element.textContent = value === undefined || value === null ? "" : String(value);
  return element;
}

export function setHidden(element, hidden) {
  element.hidden = Boolean(hidden);
  return element;
}

export function element(tagName, className, text) {
  const created = document.createElement(tagName);
  if (className) {
    created.classList.add(...String(className).split(/\s+/).filter(Boolean));
  }
  if (text !== undefined) {
    created.textContent = String(text);
  }
  return created;
}

export function appendTextElement(parent, tagName, className, value) {
  const created = element(tagName, className, value);
  parent.append(created);
  return created;
}

export function humanLabel(value) {
  const normalized = String(value ?? "")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .toLowerCase();
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function humanValue(value) {
  if (value === undefined || value === null) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map(humanValue).filter(Boolean).join(", ");
  }
  if (typeof value === "object") {
    return Object.values(value).map(humanValue).filter(Boolean).join(":");
  }
  return humanLabel(value);
}
