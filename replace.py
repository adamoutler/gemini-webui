import re

with open("src/static/app.js", "r") as f:
    content = f.read()

# The class definition
class_definition_pattern = re.compile(
    r"class MobileInputProxy \{.*?emitToTerminal\(data\) \{.*?\}\n\}", 
    re.DOTALL
)

new_classes = """class MobileInputBuffer {
  constructor(emitCallback, isMobile) {
    this.emitCallback = emitCallback;
    this.isMobile = isMobile;
  }

  handleInput(e, isComposing, value) {
    if (e.inputType === 'deleteContentBackward') {
        if (!this.isMobile) return undefined; // Desktop xterm handles backspace
        this.emitCallback('\\x7f');
        return undefined;
    }
    if (isComposing) return undefined;

    const boundaryRegex = /[\\s.,?!;-]/;
    
    // On desktop, xterm.js handles single character and paste emissions via onData.
    if (!this.isMobile && !isComposing) {
        if (e.data && e.data.length === 1) {
            // Clear buffer on boundary to reset overlay
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

  handleKeyDown(e, value) {
    if (e.altKey || e.ctrlKey || e.metaKey) {
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
}

class MobileInputUI {
  constructor(proxyInput, tabId, inputHandler, keyDownHandler) {
    this.proxyInput = proxyInput;
    this.proxyInput.id = 'terminal-input-' + tabId;
    this.proxyInput.classList.add('mobile-proxy-input');
    this.proxyInput.style.cssText = 'border: none; background: transparent !important; outline: none; color: var(--terminal-fg) !important;';
    
    this.proxyInput.setAttribute('autocomplete', 'on');
    this.proxyInput.setAttribute('autocorrect', 'on');
    this.proxyInput.setAttribute('spellcheck', 'true');
    this.proxyInput.setAttribute('autocapitalize', 'sentences');

    let isComposing = false;
    this.proxyInput.addEventListener('compositionstart', () => { 
        isComposing = true; 
        this.proxyInput.classList.add('is-composing');
    });
    this.proxyInput.addEventListener('compositionend', () => {
        isComposing = false;
        this.proxyInput.classList.remove('is-composing');
        setTimeout(() => { if (this.proxyInput.value.length > 0) this.proxyInput.value = ''; }, 200);
    });

    this.proxyInput.addEventListener('input', (e) => {
        const newValue = inputHandler(e, isComposing, this.proxyInput.value);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });
    this.proxyInput.addEventListener('keydown', (e) => {
        const newValue = keyDownHandler(e, this.proxyInput.value);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });
  }
}

class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;
    this.proxyInput = tab.term.textarea;
    
    this.isMobile = window.matchMedia('(max-width: 768px) and (pointer: coarse)').matches 
                    || 'ontouchstart' in window;
    
    if (this.proxyInput) {
      this.buffer = new MobileInputBuffer(this.emitToTerminal.bind(this), this.isMobile);
      this.ui = new MobileInputUI(this.proxyInput, this.tab.id, this.buffer.handleInput.bind(this.buffer), this.buffer.handleKeyDown.bind(this.buffer));
    }
  }

  emitToTerminal(data) {
     if (!this.tab || !this.tab.socket || data == null) return;
     const chunkSize = 1024;
     const strData = String(data).replace(/\\n/g, '\\r');
     for (let i = 0; i < strData.length; i += chunkSize) {
         const chunk = strData.slice(i, i + chunkSize);
         this.tab.socket.emit('pty-input', {input: chunk});
     }
  }
}"""

content = re.sub(class_definition_pattern, new_classes, content, count=1)
content = content.replace("new MobileInputProxy(tab);", "new MobileTerminalController(tab);")

with open("src/static/app.js", "w") as f:
    f.write(content)

print("Replacement done")