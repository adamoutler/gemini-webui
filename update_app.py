import re

with open("src/static/app.js", "r") as f:
    content = f.read()

# 1. Remove the onData modifier logic
old_ondata = """            tab.term.onData((data) => {
                if (tab.socket) {
                    let input = data;
                    if (ctrlActive && data.length === 1) {
                        const code = data.charCodeAt(0);
                        if (code >= 97 && code <= 122) { // a-z
                            input = String.fromCharCode(code - 96);
                        } else if (code >= 65 && code <= 90) { // A-Z
                            input = String.fromCharCode(code - 64);
                        }
                        toggleCtrl(false);
                    } else if (ctrlActive) {
                        toggleCtrl(false);
                    }
                    if (altActive && data.length === 1) {
                        input = '\\x1b' + input;
                        toggleAlt(false);
                    } else if (altActive) {
                        toggleAlt(false);
                    }
                    emitPtyInput(tab, input);
                }
            });"""

new_ondata = """            tab.term.onData((data) => {
                if (tab.socket) {
                    // Mobile modifiers are handled by MobileModifierState
                    // Desktop modifiers are handled natively by xterm.js via e.ctrlKey
                    emitPtyInput(tab, data);
                }
            });"""

content = content.replace(old_ondata, new_ondata)

# 2. Remove toggleCtrl / toggleAlt / setupModifierBtn
setup_btns = """        // Setup sticky modifier buttons (Ctrl/Alt)
        const setupModifierBtn = (id, toggleFn) => {
            const btn = document.getElementById(id);
            if (!btn) return;
            const handler = (e) => {
                if (e.type === 'touchstart') {
                    e.preventDefault(); // prevent mouse emulation and double click
                }
                triggerHapticFeedback();
                toggleFn();

                // Explicitly focus the terminal textarea to ensure the keyboard appears
                const tab = tabs.find(t => t.id === activeTabId);
                if (tab && tab.term && tab.term.textarea) {
                    tab.term.textarea.focus();
                }
            };
            btn.addEventListener('touchstart', handler, { passive: false });
            btn.addEventListener('mousedown', handler);
        };
        setupModifierBtn('ctrl-toggle', toggleCtrl);
        setupModifierBtn('alt-toggle', toggleAlt);"""

content = content.replace(setup_btns, "")

with open("src/static/app.js", "w") as f:
    f.write(content)

print("Done updating app.js")
