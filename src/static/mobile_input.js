class MobileModifierState {
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
            input = '\x00';
        } else if (code === 91) { // Ctrl+[
            input = '\x1b';
        } else if (code === 92) { // Ctrl+\
            input = '\x1c';
        } else if (code === 93) { // Ctrl+]
            input = '\x1d';
        }
        this.toggleCtrl(false);
    } else if (this.ctrlActive) {
        this.toggleCtrl(false);
    }
    
    if (this.altActive && data.length === 1) {
        input = '\x1b' + input;
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
        this.emitCallback('\x7f');
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

    const boundaryRegex = /[\s.,?!;-]/;
    
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


  handleKeyDown(e, value) {
    if (e.altKey || e.ctrlKey || e.metaKey) {
        if (!this.isMobile) return '';
        return undefined;
    }
    if (e.key === 'Backspace' || e.keyCode === 8) {
      if (value.length === 0) {
        if (!this.isMobile) return undefined; 
        e.preventDefault();
        this.emitCallback('\x7f');
      }
    }
    if (e.key === 'Enter') {
      if (!this.isMobile) return undefined;
      e.preventDefault();
      this.emitCallback(value + '\r');
      return '';
    }
    return undefined;
  }
}

class MobileInputUI {
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
}

class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;
    
    this.isMobile = window.matchMedia('(max-width: 768px) and (pointer: coarse)').matches 
                    || 'ontouchstart' in window;
    
    if (this.isMobile) {
      this.modifierState = new MobileModifierState();
      this.buffer = new MobileInputBuffer(this.emitToTerminal.bind(this), this.isMobile, this.modifierState);
      this.ui = new MobileInputUI(this.tab.id, this.buffer.handleInput.bind(this.buffer), this.buffer.handleKeyDown.bind(this.buffer));
    }
  }

  emitToTerminal(data) {
     if (!this.tab || !this.tab.socket || data == null) return;
     const chunkSize = 1024;
     const strData = String(data).replace(/\n/g, '\r');
     for (let i = 0; i < strData.length; i += chunkSize) {
         const chunk = strData.slice(i, i + chunkSize);
         this.tab.socket.emit('pty-input', {input: chunk});
     }
  }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MobileInputBuffer, MobileInputUI, MobileTerminalController, MobileModifierState };
}