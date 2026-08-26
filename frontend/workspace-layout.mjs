const DRAWERS = new Set(["left", "right"]);
const SECTIONS = new Set(["workspace", "work", "notes", "memory", "chats"]);
const ARTIFACT_DRAWER_MODES = new Set(["hidden", "normal", "expanded"]);

export function createInitialLayoutState() {
  return {
    artifactDrawerMode: "normal",
    drawers: {
      left: true,
      right: true,
    },
    sections: {
      workspace: false,
      work: false,
      notes: false,
      memory: false,
      chats: false,
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

export function setArtifactDrawerMode(layout, mode) {
  if (!ARTIFACT_DRAWER_MODES.has(mode)) {
    throw new Error(`Unsupported artifact drawer mode: ${mode}`);
  }
  return {
    ...layout,
    artifactDrawerMode: mode,
    drawers: {
      ...layout.drawers,
      right: mode !== "hidden",
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
  if (drawer === "right" && layout.artifactDrawerMode === "hidden") {
    return false;
  }
  return layout.drawers[drawer] === true;
}

export function isSectionExpanded(layout, section) {
  return layout.sections[section] === true;
}
