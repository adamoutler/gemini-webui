import re
import hashlib
import os


def merge_classes(m):
    tag = m.group(0)
    classes = re.findall(r'class="([^"]*)"', tag)
    if len(classes) > 1:
        merged = " ".join(classes)
        tag = re.sub(r'\s*class="[^"]*"', "", tag)
        tag = tag.replace(" ", f' class="{merged}" ', 1)
    return tag


def refactor():
    # --- index.html ---
    with open("src/templates/index.html", "r") as f:
        html = f.read()

    style_matches = re.findall(r'style="([^"]*)"', html)
    unique_styles = list(set(style_matches))
    style_map = {}
    css_lines = ["\n/* Auto-extracted inline styles for CSP */"]

    for i, style in enumerate(unique_styles):
        hash_suffix = hashlib.md5(style.encode()).hexdigest()[:6]
        class_name = f"auto-style-{hash_suffix}"
        style_map[style] = class_name
        css_lines.append(f".{class_name} {{ {style} }}")

    def replace_style(m):
        return f'class="{style_map[m.group(1)]}"'

    html = re.sub(r'style="([^"]*)"', replace_style, html)
    html = re.sub(r"<[^>]+>", merge_classes, html)

    html = re.sub(r'onclick="([^"]*)"', r'data-onclick="\1"', html)
    html = re.sub(r'onchange="([^"]*)"', r'data-onchange="\1"', html)

    with open("src/templates/index.html", "w") as f:
        f.write(html)

    # --- app.js ---
    with open("src/static/app.js", "r") as f:
        js = f.read()

    # Extract inline styles
    style_matches_js = re.findall(r'style="([^"]*)"', js)
    style_matches_sq_js = re.findall(r"style='([^']*)'", js)
    unique_styles_js = list(set(style_matches_js + style_matches_sq_js))

    style_map_js = {}
    for i, style in enumerate(unique_styles_js):
        hash_suffix = hashlib.md5(style.encode()).hexdigest()[:6]
        class_name = f"js-style-{hash_suffix}"
        style_map_js[style] = class_name
        css_lines.append(f".{class_name} {{ {style} }}")

    def replace_style_js(m):
        return f'class="{style_map_js[m.group(1)]}"'

    def replace_style_sq_js(m):
        return f"class='{style_map_js[m.group(1)]}'"

    js = re.sub(r'style="([^"]*)"', replace_style_js, js)
    js = re.sub(r"style='([^']*)'", replace_style_sq_js, js)
    js = re.sub(r"<[^>]+>", merge_classes, js)

    js = re.sub(r'(?<!data-)onclick="([^"]*)"', r'data-onclick="\1"', js)
    js = re.sub(r'(?<!data-)onchange="([^"]*)"', r'data-onchange="\1"', js)

    # Make sure we don't append multiple times
    if "function executeDataAction" not in js:
        js_lines = """
// CSP Event Delegation
function executeDataAction(code, event) {
    if (!code) return;

    if (code.startsWith("document.getElementById")) {
         if (code.includes("'import-settings-input').click()")) {
             document.getElementById('import-settings-input').click();
         }
         return;
    }
    if (code.startsWith("window.open")) {
        if (code.includes("'share-link-input'")) {
             window.open(document.getElementById('share-link-input').value, '_blank');
        }
        return;
    }
    if (code.includes("window.location.href")) {
         window.location.href = '/test-launcher';
         return;
    }
    if (code.startsWith("event.stopPropagation();")) {
         event.stopPropagation();
         code = code.replace("event.stopPropagation();", "").trim();
    }
    if (code.startsWith("window.expandedSessionLists")) {
         let match = code.match(/window\\.expandedSessionLists\\.(add|delete)\\((.*)\\)/);
         if (match) {
             let op = match[1];
             let args = match[2].split(',').map(s => {
                 s = s.trim().replace(/^['"]|['"]$/g, '');
                 if (s === 'true') return true;
                 if (s === 'false') return false;
                 return s;
             });
             if (op === 'add') window.expandedSessionLists.add(...args);
             else window.expandedSessionLists.delete(...args);
         }
         return;
    }

    let match = code.match(/^([a-zA-Z0-9_]+)\\((.*)\\)$/);
    if (match) {
        let funcName = match[1];
        let argsStr = match[2];
        let args = [];
        if (argsStr.trim()) {
            // Basic split by comma. Since we don't use nested functions or commas inside strings
            // in our inline handlers, this simple split is sufficient.
            args = argsStr.split(',').map(s => {
                s = s.trim();
                if (s === 'event') return event;
                if (s === 'true') return true;
                if (s === 'false') return false;
                if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1);
                if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
                if (!isNaN(s) && s !== '') return Number(s);
                return s;
            });
        }
        if (typeof window[funcName] === 'function') {
            window[funcName].apply(null, args);
        } else {
            console.error("Function not found: " + funcName);
        }
    } else {
        console.error("Could not parse data action: " + code);
    }
}

document.addEventListener('click', function(e) {
    let target = e.target.closest('[data-onclick]');
    if (target) {
        executeDataAction(target.getAttribute('data-onclick'), e);
    }
});

document.addEventListener('change', function(e) {
    let target = e.target.closest('[data-onchange]');
    if (target) {
        executeDataAction(target.getAttribute('data-onchange'), e);
    }
});
"""
        js += js_lines

    with open("src/static/app.js", "w") as f:
        f.write(js)

    with open("src/static/base.css", "a") as f:
        f.write("\n".join(css_lines) + "\n")


if __name__ == "__main__":
    refactor()
