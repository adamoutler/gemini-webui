# Infinite Scroll Loop - Continuity Document

## 1. Issue Description

The user reported that the scrollbar in the mobile terminal view never reaches a hard stop at the bottom. Instead, the scroll indicator goes down past the bottom, skips back to the middle, and loops perpetually. This happens because the terminal auto-scrolls to the bottom, but the dummy scroll proxy allows infinite scrolling past the terminal's logical boundaries.

## 2. Architectural Diagnosis

The `gemini-webui` project uses a "Passive Portal Implementation for Native Momentum" in `src/static/js/terminal/ui.js` (around line ~194). This creates a `mobile-scroll-proxy` div with a massive height (100,000px) and centers the `scrollTop` at `50000`.
When the user scrolls on mobile, this dummy proxy captures the native momentum scroll and calculates `deltaLines`. It then tells the underlying `xterm.js` instance to `tab.term.scrollLines(deltaLines)`.

**The Bug:**
If the `xterm.js` buffer is already at the top or bottom, `scrollLines()` does nothing. However, the dummy proxy _did_ scroll. If the user keeps dragging, the proxy's `scrollTop` eventually exceeds a boundary (`Math.abs(proxy.scrollTop - 50000) > 40000`) and forcefully resets back to `50000`. This creates the visual effect of the scrollbar skipping back to the middle and looping infinitely.

## 3. Surgical Mitigation Applied

I updated the proxy logic to check if `xterm.js` _actually_ scrolled.

```javascript
const preY = tab.term.buffer.active.viewportY;
tab.term.scrollLines(deltaLines);
const postY = tab.term.buffer.active.viewportY;

// Hard stop: if we tried to scroll but the terminal didn't move, we've hit a boundary.
if (preY === postY) {
  isSyncing = true;
  proxy.scrollTop = lastScrollTop;
  setTimeout(() => {
    isSyncing = false;
  }, 10);
  return;
}
```

If `preY === postY`, we hit a hard boundary. We revert the `proxy.scrollTop` to `lastScrollTop`, physically stopping the dummy div from scrolling into the void, which fixes the perpetual loop.

## 4. Current State & Next Steps

- The code fix is complete and committed locally in `src/static/js/terminal/ui.js`.
- During the `git push`, the CI/CD pipeline failed.
- **Next Agent Action:** You must investigate the CI/CD failure on GitHub Actions.
  Run this command to see why the build failed:
  `gh run list --workflow "build-and-publish.yml" --limit 1 --json databaseId -q ".[0].databaseId" | xargs gh run view --log-failed`
- Fix the CI failure (likely a Playwright E2E test or Python formatting issue) and push the final resolution.
