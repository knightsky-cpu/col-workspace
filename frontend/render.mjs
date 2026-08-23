export function setText(element, value) {
  element.textContent = value;
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
