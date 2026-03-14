import re

with open('src/static/app.js', 'r') as f:
    content = f.read()

# 3. Remove toggleCtrl / toggleAlt
toggles = """        function toggleCtrl(force) {
            ctrlActive = force !== undefined ? force : !ctrlActive;
            const btn = document.getElementById('ctrl-toggle');
            if (ctrlActive) btn.classList.add('active');
            else btn.classList.remove('active');
        }

        function toggleAlt(force) {
            altActive = force !== undefined ? force : !altActive;
            const btn = document.getElementById('alt-toggle');
            if (altActive) btn.classList.add('active');
            else btn.classList.remove('active');
        }"""
content = content.replace(toggles, "")

# 4. Remove variables
content = content.replace("        let ctrlActive = false;\n", "")
content = content.replace("        let altActive = false;\n", "")

# 5. Remove desktop specific clears if present (Wait, app.js still clears buffer for desktop? Yes, but MobileInputBuffer is not instantiated for desktop).
# Actually, MobileTerminalController only attaches if isMobile is true.
# The desktop input doesn't use MobileTerminalController anymore, so we don't need to clear `proxyInput.value` for modifiers there.

with open('src/static/app.js', 'w') as f:
    f.write(content)

print("Done part 2")