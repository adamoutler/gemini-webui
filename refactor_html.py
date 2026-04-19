import re

with open("src/templates/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# exact strings for start and end
parts = [
    ("toolbar.html", '    <div id="toolbar">', '    <div id="tab-bar">'),
    ("tab_bar.html", '    <div id="tab-bar"></div>\n', "    <div\n"),
    (
        "install_banner.html",
        '    <div\n      class="install-banner',
        '    <div id="terminal-container">',
    ),
    (
        "terminal_container.html",
        '    <div id="terminal-container"></div>\n',
        '    <div id="mobile-controls"',
    ),
    (
        "mobile_controls.html",
        '    <div id="mobile-controls" class="auto-style-9c7663">',
        '    <div id="file-transfer-modal"',
    ),
    (
        "modals.html",
        '    <div id="file-transfer-modal" class="modal">',
        '    <script\n      src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"',
    ),
]

for partial, start_str, end_str in parts:
    start_idx = html.find(start_str)
    end_idx = html.find(end_str)
    if start_idx != -1 and end_idx != -1:
        content = html[start_idx:end_idx]
        with open(f"src/templates/partials/{partial}", "w", encoding="utf-8") as f:
            f.write(content)
        html = (
            html[:start_idx]
            + f"    {{% include 'partials/{partial}' %}}\n"
            + html[end_idx:]
        )

with open("src/templates/index.html", "w", encoding="utf-8") as f:
    f.write(html)
