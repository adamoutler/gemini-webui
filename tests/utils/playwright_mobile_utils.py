import time


def simulateAutocorrect(page, old_word, new_word, locator=".mobile-text-area"):
    """
    Simulates a mobile OS autocorrecting a word.
    Changes the value of the textarea and fires an input event.
    """
    page.evaluate(f"""
        () => {{
            const el = document.querySelector('{locator}');
            if (el) {{
                const val = el.value;
                const lastIndex = val.lastIndexOf('{old_word}');
                if (lastIndex !== -1) {{
                    el.value = val.substring(0, lastIndex) + '{new_word}' + val.substring(lastIndex + {len(old_word)});
                }} else {{
                    el.value = val + '{new_word}';
                }}
                el.dispatchEvent(new InputEvent('input', {{ inputType: 'insertReplacementText' }}));
            }}
        }}
    """)
    time.sleep(0.1)


def simulateSpacebarTrackpad(page, offset, locator=".mobile-text-area"):
    """
    Simulates using the spacebar as a trackpad to move the cursor left/right.
    Changes the selectionStart/selectionEnd and fires selectionchange.
    """
    page.evaluate(f"""
        () => {{
            const el = document.querySelector('{locator}');
            if (el) {{
                const newPos = Math.max(0, el.selectionStart + ({offset}));
                el.setSelectionRange(newPos, newPos);
                document.dispatchEvent(new Event('selectionchange'));
            }}
        }}
    """)
    time.sleep(0.1)


