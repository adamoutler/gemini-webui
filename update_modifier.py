with open("src/static/mobile_input.js", "r") as f:
    content = f.read()

import re
old_text = re.search(r"class MobileInputBuffer \{.*?handleInput\(e, isComposing, value\) \{.*?return undefined;\n  \}", content, re.DOTALL).group(0)

new_classes = """class MobileModifierState {
  constructor() {
    this.ctrlActive = false;
    this.altActive = false;
    this.ctrlBtn = document.getElementById('ctrl-toggle');
    this.altBtn = document.getElementById('alt-toggle');
    this.setupListeners();
  }
  
  setupListeners() {
    const bindBtn = (btn, toggleFn) => {
        if (!btn) return;
        const handler = (e) => {
            if (e.type === 'touchstart') e.preventDefault();
            if (window.triggerHapticFeedback) window.triggerHapticFeedback();
            toggleFn();
            const activeProxy = document.querySelector('.mobile-proxy-input');
            if (activeProxy) activeProxy.focus();
        };
        btn.addEventListener('touchstart', handler, { passive: false });
        btn.addEventListener('mousedown', handler);
    };
    bindBtn(this.ctrlBtn, () => this.toggleCtrl());
    bindBtn(this.altBtn, () => this.toggleAlt());
  }

  toggleCtrl(force) {
    this.ctrlActive = force !== undefined ? force : !this.ctrlActive;
    if (this.ctrlBtn) {
        if (this.ctrlActive) this.ctrlBtn.classList.add('active');
        else this.ctrlBtn.classList.remove('active');
    }
  }

  toggleAlt(force) {
    this.altActive = force !== undefined ? force : !this.altActive;
    if (this.altBtn) {
        if (this.altActive) this.altBtn.classList.add('active');
        else this.altBtn.classList.remove('active');
    }
  }

  applyModifiers(data) {
    if (!data) return data;
    let input = data;
    if (this.ctrlActive && data.length === 1) {
        const code = data.charCodeAt(0);
        if (code >= 97 && code <= 122) { // a-z
            input = String.fromCharCode(code - 96);
        } else if (code >= 65 && code <= 90) { // A-Z
            input = String.fromCharCode(code - 64);
        } else if (code === 32) { // Ctrl+Space
            input = '\\x00';
        } else if (code === 91) { // Ctrl+[
            input = '\\x1b';
        } else if (code === 92) { // Ctrl+\\
            input = '\\x1c';
        } else if (code === 93) { // Ctrl+]
            input = '\\x1d';
        }
        this.toggleCtrl(false);
    } else if (this.ctrlActive) {
        this.toggleCtrl(false);
    }
    
    if (this.altActive && data.length === 1) {
        input = '\\x1b' + input;
        this.toggleAlt(false);
    } else if (this.altActive) {
        this.toggleAlt(false);
    }
    return input;
  }
}

class MobileInputBuffer {
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
    if (isComposing) return undefined;

    if (this.modifierState && (this.modifierState.ctrlActive || this.modifierState.altActive)) {
        if (e.data && e.data.length > 0) {
             const char = e.data[e.data.length - 1]; 
             const modified = this.modifierState.applyModifiers(char);
             this.emitCallback(modified);
             return ''; 
        }
    }

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
"""

content = content.replace(old_text, new_classes)
with open("src/static/mobile_input.js", "w") as f:
    f.write(content)
print("done")
