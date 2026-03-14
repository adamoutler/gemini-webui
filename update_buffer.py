import re

with open("src/static/mobile_input.js", "r") as f:
    content = f.read()

new_buffer = """class MobileInputBuffer {
  constructor(emitCallback, isMobile, modifierState) {
    this.emitCallback = emitCallback;
    this.isMobile = isMobile;
    this.modifierState = modifierState;
  }

  handleInput(e, isComposing, value) {
    if (e.inputType === 'deleteContentBackward') {
        if (!this.isMobile) return undefined;
        this.emitCallback('\\x7f');
        return undefined;
    }
    
    // If modifiers are active, consume exactly 1 char from data, apply modifiers, emit, clear buffer
    if (this.modifierState && (this.modifierState.ctrlActive || this.modifierState.altActive)) {
        if (e.data && e.data.length > 0) {
             const char = e.data[e.data.length - 1]; 
             const modified = this.modifierState.applyModifiers(char);
             this.emitCallback(modified);
             return ''; 
        }
    }

    if (isComposing) return undefined;

    const boundaryRegex = /[\\s.,?!;-]/;
    
    if (!this.isMobile && !isComposing) {
        if (e.data && e.data.length === 1) {
            if (boundaryRegex.test(e.data)) {
                return '';
            }
            return undefined;
        }
    }

    if (boundaryRegex.test(value) || (!this.isMobile && value.length > 1)) {
      this.emitCallback(value);
      return '';
    }
    return undefined;
  }

  handleKeyDown(e, value, isComposing) {
    if (isComposing) return undefined;

    const passthroughKeys = {
      'Tab': '\\t',
      'Escape': '\\x1b'
    };

    if (passthroughKeys[e.key]) {
      e.preventDefault();
      if (e.key === 'Escape') {
          this.emitCallback(passthroughKeys[e.key]);
          return ''; // clear buffer without sending current value
      } else {
          // send current buffer + the passthrough key
          this.emitCallback(value + passthroughKeys[e.key]);
          return ''; 
      }
    }

    if (e.altKey || e.ctrlKey || e.metaKey) {
        // e.g. real physical keyboard Ctrl+C on mobile
        if (e.ctrlKey && e.key.toLowerCase() === 'c') {
            e.preventDefault();
            this.emitCallback('\\x03');
            return ''; // clear buffer
        }
        if (!this.isMobile) return '';
        return undefined;
    }
    
    if (e.key === 'Backspace' || e.keyCode === 8) {
      if (value.length === 0) {
        if (!this.isMobile) return undefined; 
        e.preventDefault();
        this.emitCallback('\\x7f');
      }
    }
    if (e.key === 'Enter') {
      if (!this.isMobile) return undefined;
      e.preventDefault();
      this.emitCallback(value + '\\r');
      return '';
    }
    return undefined;
  }
}"""

content = re.sub(r"class MobileInputBuffer \{.*?handleKeyDown\(e, value\) \{.*?return undefined;\n  \}\n\}", new_buffer, content, flags=re.DOTALL)

ui_event_replace = """    this.proxyInput.addEventListener('keydown', (e) => {
        const newValue = keyDownHandler(e, this.proxyInput.value, this.isComposing);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });"""

content = re.sub(r"    this\.proxyInput\.addEventListener\('keydown', \(e\) => \{\n        const newValue = keyDownHandler\(e, this\.proxyInput\.value\);\n        if \(newValue !== undefined\) this\.proxyInput\.value = newValue;\n    \}\);", ui_event_replace, content)


with open("src/static/mobile_input.js", "w") as f:
    f.write(content)
print("done")
