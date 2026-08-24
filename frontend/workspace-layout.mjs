const DRAWERS = new Set(["left", "right"]);
const SECTIONS = new Set(["work", "memory", "activity"]);

export function createInitialLayoutState() {
  return {
    drawers: {
      left: true,
      right: true,
    },
    sections: {
      work: true,
      memory: true,
      activity: true,
    },
  };
}

export function setDrawerCollapsed(layout, drawer, collapsed) {
  if (!DRAWERS.has(drawer)) {
    throw new Error(`Unsupported drawer: ${drawer}`);
  }
  return {
    ...layout,
    drawers: {
      ...layout.drawers,
      [drawer]: !collapsed,
    },
  };
}

export function setSectionExpanded(layout, section, expanded) {
  if (!SECTIONS.has(section)) {
    throw new Error(`Unsupported section: ${section}`);
  }
  return {
    ...layout,
    sections: {
      ...layout.sections,
      [section]: expanded,
    },
  };
}

export function isDrawerExpanded(layout, drawer) {
  return layout.drawers[drawer] === true;
}

export function isSectionExpanded(layout, section) {
  return layout.sections[section] === true;
}
