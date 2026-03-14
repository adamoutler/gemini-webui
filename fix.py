import re

with open("src/static/mobile_input.js", "r") as f:
    content = f.read()

new_ui = """class MobileInputUI {
  constructor(tabId, inputHandler, keyDownHandler) {
    this.proxyInput = document.createElement('input');
    this.proxyInput.id = 'terminal-input-' + tabId;
    this.proxyInput.classList.add('mobile-proxy-input');
    this.proxyInput.style.cssText = 'position: absolute; border: none; background: transparent !important; outline: none; color: var(--terminal-fg) !important; width: 1px; height: 1px; opacity: 0;';
    
    this.proxyInput.setAttribute('autocomplete', 'on');
    this.proxyInput.setAttribute('autocorrect', 'on');
    this.proxyInput.setAttribute('spellcheck', 'true');
    this.proxyInput.setAttribute('autocapitalize', 'sentences');

    // Basic DOM attachment (will be fully positioned in Ticket 4)
    if (document.body) {
        document.body.appendChild(this.proxyInput);
    }

    this.isComposing = false;
    this.proxyInput.addEventListener('compositionstart', () => { 
        this.isComposing = true; 
        this.proxyInput.classList.add('is-composing');
    });
    this.proxyInput.addEventListener('compositionend', () => {
        this.isComposing = false;
        this.proxyInput.classList.remove('is-composing');
        setTimeout(() => { if (this.proxyInput.value.length > 0) this.proxyInput.value = ''; }, 200);
    });

    this.proxyInput.addEventListener('input', (e) => {
        const newValue = inputHandler(e, this.isComposing, this.proxyInput.value);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });
    this.proxyInput.addEventListener('keydown', (e) => {
        const newValue = keyDownHandler(e, this.proxyInput.value);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });
  }
}"""

content = re.sub(r"class MobileInputUI \{.*?\}\n\}", new_ui, content, flags=re.DOTALL)

# Also update MobileTerminalController
new_controller = """class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;
    
    this.isMobile = window.matchMedia('(max-width: 768px) and (pointer: coarse)').matches 
                    || 'ontouchstart' in window;
    
    if (this.isMobile) {
      this.buffer = new MobileInputBuffer(this.emitToTerminal.bind(this), this.isMobile);
      this.ui = new MobileInputUI(this.tab.id, this.buffer.handleInput.bind(this.buffer), this.buffer.handleKeyDown.bind(this.buffer));
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
content = re.sub(r"class MobileTerminalController \{.*?\}\n\}", new_controller, content, flags=re.DOTALL)

with open("src/static/mobile_input.js", "w") as f:
    f.write(content)
print("Updated classes")
