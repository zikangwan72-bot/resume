# Offline Web Prototype Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and package complete static and interactive offline prototypes for Enterprise AI Suite.

**Architecture:** Reuse verified application screenshots as immutable visual assets. Build one self-contained HTML navigator driven by a page manifest, then validate every referenced image before creating the desktop ZIP.

**Tech Stack:** Playwright screenshots, HTML/CSS/JavaScript, PowerShell packaging.

## Global Constraints

- Output must run offline without backend services.
- Static assets cover desktop and mobile.
- Dynamic prototype must use real application screenshots.
- Final folder and ZIP must be placed on the Windows desktop.

---

### Task 1: Assemble the screenshot inventory

**Files:**
- Create: `artifacts/prototype-package/page-inventory.csv`
- Create: `artifacts/prototype-package/static/desktop/*.png`
- Create: `artifacts/prototype-package/static/mobile/*.png`

- [ ] Copy verified screenshots into normalized desktop and mobile directories.
- [ ] Add key asset-management drawer and workflow states.
- [ ] Verify every inventory row has an existing image.

### Task 2: Build the offline dynamic navigator

**Files:**
- Create: `artifacts/prototype-package/dynamic/index.html`

- [ ] Define the page manifest with module, route, description and test points.
- [ ] Render module filters, page navigation and device controls.
- [ ] Add keyboard-safe previous and next controls.
- [ ] Verify all images load with zero broken references.

### Task 3: Document and package the deliverable

**Files:**
- Create: `artifacts/prototype-package/README.md`
- Create: `Desktop/Enterprise-AI-Suite-Web-Prototypes.zip`

- [ ] Document how to open the static and dynamic prototypes.
- [ ] Copy the package directory to the desktop.
- [ ] Compress the directory and verify the ZIP file list.
