import os

with open("src/static/base.css", "r", encoding="utf-8") as f:
    css_content = f.read()

# Let's find some split points.
# split 1: right before `#terminal-container`
split1_idx = css_content.find("#terminal-container {")
# split 2: right before `.session-list-container`
split2_idx = css_content.find(".session-list-container {")

part1 = css_content[:split1_idx]
part2 = css_content[split1_idx:split2_idx]
part3 = css_content[split2_idx:]

with open("src/static/design-system.css", "w", encoding="utf-8") as f:
    f.write(part1)

with open("src/static/layout.css", "w", encoding="utf-8") as f:
    f.write(part2)

with open("src/static/components.css", "w", encoding="utf-8") as f:
    f.write(part3)

new_base = """@import url('./design-system.css');
@import url('./layout.css');
@import url('./components.css');
"""

with open("src/static/base.css", "w", encoding="utf-8") as f:
    f.write(new_base)

print("CSS split successfully.")
