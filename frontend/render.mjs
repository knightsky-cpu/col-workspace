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
    created.classList.add(className);
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
