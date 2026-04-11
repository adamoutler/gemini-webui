import re
import hashlib


def refactor_js():
    with open("src/static/app.js", "r") as f:
        js = f.read()

    # 1. Extract inline styles
    style_matches = re.findall(r'style="([^"]*)"', js)
    # also handle single quotes style='...'
    style_matches_sq = re.findall(r"style='([^']*)'", js)

    unique_styles = list(set(style_matches + style_matches_sq))

    style_map = {}
    css_lines = []
    for i, style in enumerate(unique_styles):
        hash_suffix = hashlib.md5(style.encode()).hexdigest()[:6]
        class_name = f"js-style-{hash_suffix}"
        style_map[style] = class_name
        css_lines.append(f".{class_name} {{ {style} }}")

    def replace_style(m):
        style_content = m.group(1)
        class_name = style_map[style_content]
        return f'class="{class_name}"'

    def replace_style_sq(m):
        style_content = m.group(1)
        class_name = style_map[style_content]
        return f"class='{class_name}'"

    js = re.sub(r'style="([^"]*)"', replace_style, js)
    js = re.sub(r"style='([^']*)'", replace_style_sq, js)

    # Note: JS template literals might have `class="foo" class="bar"`. We can do a simplistic merge.
    # But doing this on JS source is risky because it might match JS code like `a.class="b" + c.class="d"`.
    # Let's restrict it to strings enclosed in `<...>`
    def merge_classes(m):
        tag = m.group(0)
        classes = re.findall(r'class="([^"]*)"', tag)
        if len(classes) > 1:
            merged = " ".join(classes)
            tag = re.sub(r'\s*class="[^"]*"', "", tag)
            tag = tag.replace(" ", f' class="{merged}" ', 1)
        return tag

    js = re.sub(r"<[^>]+>", merge_classes, js)

    with open("src/static/app.js", "w") as f:
        f.write(js)

    with open("src/static/base.css", "a") as f:
        f.write("\n/* Auto-extracted inline styles from JS for CSP */\n")
        f.write("\n".join(css_lines))
        f.write("\n")


if __name__ == "__main__":
    refactor_js()
