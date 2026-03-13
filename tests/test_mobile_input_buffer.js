const assert = require('assert');

// Mock DOM
global.document = {
  body: {
    appendChild: function(child) {
      this.children = this.children || [];
      this.children.push(child);
    }
  },
  createElement: function(tag) {
    return {
      tagName: tag,
      classList: {
        add: function(cls) { this.classes = this.classes || []; this.classes.push(cls); },
        remove: function(cls) { if(this.classes) this.classes = this.classes.filter(c => c !== cls); }
      },
      style: { setProperty: function() {}, cssText: '' },
      setAttribute: function(k, v) { this[k] = v; },
      addEventListener: function(evt, cb) {
        this.listeners = this.listeners || {};
        this.listeners[evt] = cb;
      },
      value: ''
    };
  }
};

global.window = {
  matchMedia: function(q) {
    return { matches: true }; // Force mobile
  }
};

const { MobileInputBuffer, MobileInputUI, MobileTerminalController } = require('../src/static/mobile_input.js');

let emitted = [];
let buffer = new MobileInputBuffer((data) => emitted.push(data), true); // isMobile = true

// Test empty backspace
buffer.handleKeyDown({key: 'Backspace', preventDefault: () => {}}, '');
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], '\x7f');
emitted = [];

// Test boundary regex input
let newValue = buffer.handleInput({data: ' '}, false, 'hello ');
assert.strictEqual(newValue, '');
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], 'hello ');
emitted = [];

// Test composition
newValue = buffer.handleInput({data: 'x'}, true, 'x');
assert.strictEqual(newValue, undefined); // value untouched
assert.strictEqual(emitted.length, 0);

// Test MobileInputUI
let ui = new MobileInputUI('testTab', () => {}, () => {});
assert.strictEqual(ui.proxyInput.tagName, 'input');
assert.strictEqual(ui.proxyInput.id, 'terminal-input-testTab');
assert.ok(ui.proxyInput.style.cssText.includes('border: none'));
assert.ok(ui.proxyInput.style.cssText.includes('transparent'));
assert.ok(ui.proxyInput.style.cssText.includes('outline: none'));

// Test MobileTerminalController
let mockTab = {
  id: 'tab123',
  socket: {
    emit: function(event, data) {
      this.emitted = this.emitted || [];
      this.emitted.push({event, data});
    }
  }
};
let controller = new MobileTerminalController(mockTab);
controller.emitToTerminal('hello');
assert.strictEqual(mockTab.socket.emitted.length, 1);
assert.strictEqual(mockTab.socket.emitted[0].event, 'pty-input');
assert.strictEqual(mockTab.socket.emitted[0].data.input, 'hello');

console.log("All unit tests passed. CSS verified. Initialization verified.");