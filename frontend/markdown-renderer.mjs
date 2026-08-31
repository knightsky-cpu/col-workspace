import { element, setText } from "./render.mjs";

const BLOCK_TAGS = new Set(["blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "ol", "p", "pre", "table", "ul"]);
const INLINE_PATTERNS = [
  { kind: "code", expression: /`([^`\n]+)`/ },
  { kind: "strong", expression: /\*\*([^*\n]+)\*\*/ },
  { kind: "link", expression: /\[([^\]\n]+)\]\(([^)\s]+)\)/ },
];

function blockName(node) {
  return String(node.localName ?? node.tagName ?? "").toLowerCase();
}

function appendText(parent, text) {
  if (!text) {
    return;
  }
  parent.append(document.createTextNode(text));
}

function isSafeLinkHref(value) {
  try {
    const url = new URL(value, globalThis.location?.href ?? "http://localhost/");
    return ["http:", "https:", "mailto:"].includes(url.protocol);
  } catch {
    return false;
  }
}

function findNextInlineToken(text) {
  let next = null;
  for (const pattern of INLINE_PATTERNS) {
    const match = pattern.expression.exec(text);
    if (!match) {
      continue;
    }
    if (next === null || match.index < next.match.index) {
      next = { ...pattern, match };
    }
  }
  return next;
}

function appendInline(parent, text) {
  let remaining = String(text ?? "");
  while (remaining) {
    const token = findNextInlineToken(remaining);
    if (!token) {
      appendText(parent, remaining);
      return;
    }

    appendText(parent, remaining.slice(0, token.match.index));
    if (token.kind === "code") {
      parent.append(element("code", "markdown-inline-code", token.match[1]));
    } else if (token.kind === "strong") {
      const strong = element("strong", "");
      appendInline(strong, token.match[1]);
      parent.append(strong);
    } else if (isSafeLinkHref(token.match[2])) {
      const link = element("a", "markdown-link");
      link.setAttribute("href", token.match[2]);
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
      appendInline(link, token.match[1]);
      parent.append(link);
    } else {
      appendInline(parent, token.match[1]);
    }
    remaining = remaining.slice(token.match.index + token.match[0].length);
  }
}

function appendParagraph(container, lines) {
  const text = lines.join(" ").trim();
  if (!text) {
    return;
  }
  const paragraph = element("p", "markdown-paragraph");
  appendInline(paragraph, text);
  container.append(paragraph);
}

function appendHeading(container, line) {
  const match = /^(#{1,6})\s+(.+)$/.exec(line);
  if (!match) {
    return false;
  }
  const level = match[1].length;
  const heading = element(`h${level}`, `markdown-heading markdown-heading--${level}`);
  appendInline(heading, match[2].trim());
  container.append(heading);
  return true;
}

function appendHorizontalRule(container) {
  container.append(element("hr", "markdown-rule"));
}

function appendList(container, lines, ordered = false) {
  const list = element(ordered ? "ol" : "ul", "markdown-list");
  for (const line of lines) {
    const marker = ordered ? /^\d+\.\s+/ : /^[-*]\s+/;
    const item = element("li", "markdown-list-item");
    appendInline(item, line.replace(marker, "").trim());
    list.append(item);
  }
  container.append(list);
}

function appendCodeBlock(container, language, lines) {
  const pre = element("pre", "markdown-code-block");
  const code = element("code", language ? `language-${language}` : "");
  setText(code, lines.join("\n"));
  pre.append(code);
  container.append(pre);
}

function splitTableLine(line) {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function appendTable(container, lines) {
  const table = element("table", "markdown-table");
  const thead = element("thead", "");
  const tbody = element("tbody", "");
  const headerRow = element("tr", "");
  for (const header of splitTableLine(lines[0])) {
    const cell = element("th", "");
    appendInline(cell, header);
    headerRow.append(cell);
  }
  thead.append(headerRow);

  for (const line of lines.slice(2)) {
    const row = element("tr", "");
    for (const value of splitTableLine(line)) {
      const cell = element("td", "");
      appendInline(cell, value);
      row.append(cell);
    }
    tbody.append(row);
  }

  table.append(thead, tbody);
  container.append(table);
}

function collectWhile(lines, start, predicate) {
  const collected = [];
  let index = start;
  while (index < lines.length && predicate(lines[index])) {
    collected.push(lines[index]);
    index += 1;
  }
  return { collected, index };
}

export function renderSafeMarkdown(container, source) {
  container.replaceChildren();
  const root = element("div", "markdown-content");
  const lines = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  let paragraph = [];
  let index = 0;

  function flushParagraph() {
    appendParagraph(root, paragraph);
    paragraph = [];
  }

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      index += 1;
      continue;
    }

    if (/^```/.test(trimmed)) {
      flushParagraph();
      const language = trimmed.replace(/^```/, "").trim().replace(/[^\w-]/g, "");
      const codeLines = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      appendCodeBlock(root, language, codeLines);
      continue;
    }

    if (/^(#{1,6})\s+/.test(trimmed)) {
      flushParagraph();
      appendHeading(root, trimmed);
      index += 1;
      continue;
    }

    if (/^(?:---|\*\*\*|___)$/.test(trimmed)) {
      flushParagraph();
      appendHorizontalRule(root);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushParagraph();
      const result = collectWhile(lines, index, (value) => /^[-*]\s+/.test(value.trim()));
      appendList(root, result.collected.map((value) => value.trim()));
      index = result.index;
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      flushParagraph();
      const result = collectWhile(lines, index, (value) => /^\d+\.\s+/.test(value.trim()));
      appendList(root, result.collected.map((value) => value.trim()), true);
      index = result.index;
      continue;
    }

    if (
      trimmed.includes("|")
      && index + 1 < lines.length
      && isTableSeparator(lines[index + 1].trim())
    ) {
      flushParagraph();
      const tableLines = [trimmed, lines[index + 1].trim()];
      index += 2;
      while (index < lines.length && lines[index].trim().includes("|")) {
        tableLines.push(lines[index].trim());
        index += 1;
      }
      appendTable(root, tableLines);
      continue;
    }

    paragraph.push(trimmed);
    index += 1;
  }

  flushParagraph();
  if (root.children.length === 0) {
    appendText(root, String(source ?? ""));
  }
  for (const child of Array.from(root.children)) {
    if (BLOCK_TAGS.has(blockName(child))) {
      container.append(child);
    }
  }
}
