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
            if (e.type === 'touchstart' || e.type === 'touchend') e.preventDefault();
            // only toggle on touchstart or mousedown, avoid double toggle
            if (e.type === 'touchstart' || e.type === 'mousedown') {
                if (window.triggerHapticFeedback) window.triggerHapticFeedback();
                toggleFn();
                const activeProxy = document.querySelector('.mobile-proxy-input');
                if (activeProxy) activeProxy.focus();
            }
        };
        btn.addEventListener('touchstart', handler, { passive: false });
        btn.addEventListener('touchend', handler, { passive: false });
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

    // If modifiers are active, consume exactly 1 char from data, apply modifiers, emit, clear buffer
    if (this.modifierState && (this.modifierState.ctrlActive || this.modifierState.altActive)) {
        const char = (e.data && e.data.length > 0) ? e.data[e.data.length - 1] : (value ? value.slice(-1) : null);
        if (char) {
             const modified = this.modifierState.applyModifiers(char);
             this.emitCallback(modified);
             return '';
        }
    }
    if (isComposing) return undefined;

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

  handleKeyDown(e, value, isComposing) {
    const passthroughKeys = {
      'Tab': '\t',
      'Escape': '\x1b'
    };

    // If it's an explicit control key, process it even if composing.
    if (passthroughKeys[e.key]) {
      e.preventDefault();
      if (e.key === 'Escape') {
          this.emitCallback(passthroughKeys[e.key]);
          return ''; // clear buffer
      } else {
          // Tab completely bypasses buffer, but does not clear it
          this.emitCallback(passthroughKeys[e.key]);
          return undefined; // leave buffer intact
      }
    }

    if (e.altKey || e.ctrlKey || e.metaKey) {
        if (e.key && e.key.length === 1 && !e.metaKey) {
            e.preventDefault();
            let input = e.key;
            if (e.ctrlKey) {
                const code = input.charCodeAt(0);
                if (code >= 97 && code <= 122) input = String.fromCharCode(code - 96);
                else if (code >= 65 && code <= 90) input = String.fromCharCode(code - 64);
            }
            if (e.altKey) {
                input = '\x1b' + input;
            }
            this.emitCallback(input);
            return ''; // Ctrl/Alt clear buffer
        }
        if (!this.isMobile) return '';
        return undefined;
    }

    if (isComposing) return undefined;

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

    // DOM attachment
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

        // Ticket 5: Dictation detection & auto-commit
        if (this.dictationTimer) clearTimeout(this.dictationTimer);

        if (this.proxyInput.value.length > 0) {
            const isDictation = e.inputType === 'insertDictationResult' || (e.data && e.data.length > 5 && e.inputType !== 'insertFromPaste');
            if (isDictation) {
                this.proxyInput.style.width = 'calc(100vw - 20px)';
                this.proxyInput.style.left = '10px';
            }

            // Auto-commit buffer after pause
            this.dictationTimer = setTimeout(() => {
                if (this.proxyInput.value.length > 0) {
                    // force flush by appending a space
                    inputHandler({data: ' '}, false, this.proxyInput.value + ' ');
                    this.proxyInput.value = '';
                }
            }, isDictation ? 800 : 2000);
        }
    });
    this.proxyInput.addEventListener('keydown', (e) => {
        const newValue = keyDownHandler(e, this.proxyInput.value, this.isComposing);
        if (newValue !== undefined) this.proxyInput.value = newValue;
    });
  }

  alignWithCursor(term) {
    if (!term || !term.element) return;
    const cursor = term.element.querySelector('.xterm-cursor');
    if (!cursor) return;

    const cursorRect = cursor.getBoundingClientRect();
    const vv = window.visualViewport;

    // We get terminal typography
    const screenElement = term.element.querySelector('.xterm-screen');
    if (screenElement) {
        const computedStyle = window.getComputedStyle(screenElement);
        this.proxyInput.style.fontSize = computedStyle.fontSize;
        this.proxyInput.style.fontFamily = computedStyle.fontFamily;
        this.proxyInput.style.letterSpacing = computedStyle.letterSpacing;
        this.proxyInput.style.lineHeight = computedStyle.lineHeight;
    }

    // Set position
    // getBoundingClientRect is relative to the visual viewport.
    // To get document-absolute coordinates, we add the visual viewport's page offset.
    const pageTop = vv ? vv.pageTop : window.scrollY;
    const pageLeft = vv ? vv.pageLeft : window.scrollX;

    const top = cursorRect.top + pageTop;
    const left = cursorRect.left + pageLeft;

    this.proxyInput.style.transform = `translate(${left}px, ${top}px)`;

    if (this.proxyInput.value.length > 0) {
        this.proxyInput.style.opacity = '1';
        this.proxyInput.style.width = `calc(100vw - ${left}px - 20px)`;
    } else {
        this.proxyInput.style.opacity = '0';
        this.proxyInput.style.width = '1px';
    }
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

      this.setupFocusManagement();
    }
  }

  setupFocusManagement() {
    if (!this.tab.term) return;

    // Intercept touch events on terminal to focus our proxy instead
    this.tab.term.element.addEventListener('touchstart', (e) => {
        if (!e.target.closest('.xterm-viewport')) {
            e.preventDefault(); // disable xterm's native textarea behavior
            this.ui.proxyInput.focus();
            this.ui.alignWithCursor(this.tab.term);
        }
    });

    // Update alignment when cursor moves
    this.tab.term.onCursorMove(() => {
        this.ui.alignWithCursor(this.tab.term);
    });

    // Update alignment when proxy input changes (in case width/opacity needs changing)
    this.ui.proxyInput.addEventListener('input', () => {
        this.ui.alignWithCursor(this.tab.term);
    });

    // Re-align on resize or scroll
    window.addEventListener('resize', () => this.ui.alignWithCursor(this.tab.term));
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', () => this.ui.alignWithCursor(this.tab.term));
        window.visualViewport.addEventListener('scroll', () => this.ui.alignWithCursor(this.tab.term));
    }
  }

  emitToTerminal(data) {
     if (!this.tab || !this.tab.socket || data == null) return;
     if (window.emitPtyInput) {
         window.emitPtyInput(this.tab, data);
     } else {
         const chunkSize = 1024;
         const strData = String(data).replace(/\n/g, '\r');
         for (let i = 0; i < strData.length; i += chunkSize) {
             const chunk = strData.slice(i, i + chunkSize);
             this.tab.socket.emit('pty-input', {input: chunk});
         }
     }
  }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MobileInputBuffer, MobileInputUI, MobileTerminalController, MobileModifierState };
}
