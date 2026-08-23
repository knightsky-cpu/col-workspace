export function setText(element, value) {
  element.textContent = value;
  return element;
}

export function setHidden(element, hidden) {
  element.hidden = Boolean(hidden);
  return element;
}
