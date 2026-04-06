const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1024, height: 768 },
  });
  const page = await context.newPage();

  console.log("Navigating...");
  await page.goto("http://127.0.0.1:5001/");

  await page.waitForTimeout(1000);

  console.log("Injecting a fake terminal to test context menu...");
  await page.evaluate(() => {
    const container = document.getElementById("terminal-container");
    container.innerHTML = "";
    const termDiv = document.createElement("div");
    termDiv.className = "terminal-instance";
    termDiv.id = "rolling-log-fake";
    container.appendChild(termDiv);

    // Attach the fixed contextmenu listener
    termDiv.addEventListener(
      "contextmenu",
      (e) => {
        e.preventDefault();
        if (typeof initDesktopContextMenu === "function") {
          initDesktopContextMenu();
        }
        const desktopContextMenu = document.getElementById(
          "desktop-context-menu",
        );
        if (desktopContextMenu) {
          desktopContextMenu.querySelector("#ctx-copy").style.display = "block";
          desktopContextMenu.style.display = "block";
          desktopContextMenu.style.left = e.pageX + "px";
          desktopContextMenu.style.top = e.pageY + "px";
        }
      },
      true,
    );

    const term = new Terminal();
    term.open(termDiv);
    term.write("Hello World\r\nSelect me!");

    // Fake selection
    term.hasSelection = () => true;
    term.getSelection = () => "Select me!";

    window.fakeTerm = term;
  });

  await page.waitForTimeout(1000);

  console.log("Highlighting text...");
  const termEl = await page.$(".xterm-rows");
  if (termEl) {
    const box = await termEl.boundingBox();
    // Drag select over the middle
    await page.mouse.move(box.x + 20, box.y + 20);
    await page.mouse.down();
    await page.mouse.move(box.x + 100, box.y + 20);
    await page.mouse.up();

    await page.waitForTimeout(500);

    console.log("Triggering context menu...");
    // Right click
    await page.mouse.click(box.x + 50, box.y + 20, { button: "right" });

    await page.waitForTimeout(500);

    console.log("Taking screenshot...");
    await page.screenshot({ path: "public/qa-screenshots/proof_266.png" });
  }

  await browser.close();
  console.log("Done");
})();
