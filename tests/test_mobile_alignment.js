const assert = require('assert');

class MockElement {
  constructor(tag, id) {
    this.tagName = tag;
    this.id = id;
    this.classes = [];
    this.listeners = {};
    this.style = { setProperty: function() {}, cssText: '' };
    this.value = '';
    this.classList = {
      add: (cls) => { this.classes.push(cls); },
      remove: (cls) => { this.classes = this.classes.filter(c => c !== cls); },
      contains: (cls) => { return this.classes.includes(cls); }
    };
  }
  setAttribute(k, v) { this[k] = v; }
  focus() {}
  addEventListener(evt, cb) {
    this.listeners[evt] = this.listeners[evt] || [];
    this.listeners[evt].push(cb);
  }
  dispatchEvent(evtObj) {
    if (this.listeners[evtObj.type]) {
      for (const cb of this.listeners[evtObj.type]) {
        cb(evtObj);
      }
    }
  }
  querySelector(sel) {
      if (sel === '.xterm-cursor') {
          return {
              getBoundingClientRect: () => ({ top: 100, left: 50 })
          };
      }
      if (sel === '.xterm-screen') {
          return {};
      }
      return null;
  }
}

let mockCtrlBtn = new MockElement('button', 'ctrl-toggle');
let mockAltBtn = new MockElement('button', 'alt-toggle');

global.document = {
  body: {
    children: [],
    appendChild: function(child) { this.children.push(child); }
  },
  getElementById: function(id) {
    if (id === 'ctrl-toggle') return mockCtrlBtn;
    if (id === 'alt-toggle') return mockAltBtn;
    return null;
  },
  createElement: function(tag) { return new MockElement(tag, ''); },
  querySelector: function(sel) { return new MockElement('input', ''); }
};

global.window = {
  matchMedia: function(q) { return { matches: true }; },
  visualViewport: { pageTop: 10, pageLeft: 5 },
  scrollY: 20,
  scrollX: 10,
  getComputedStyle: function(el) {
      return { fontSize: '14px', fontFamily: 'monospace', letterSpacing: '1px', lineHeight: '20px' };
  }
};

const { MobileInputBuffer, MobileInputUI, MobileTerminalController, MobileModifierState } = require('../src/static/mobile_input.js');

let ui = new MobileInputUI('testTab', () => {}, () => {});
let mockTerm = { element: new MockElement('div', 'term') };

// Test alignWithCursor calculation
ui.alignWithCursor(mockTerm);

// top = cursor.top(100) + vv.pageTop(10) = 110
// left = cursor.left(50) + vv.pageLeft(5) = 55
assert.strictEqual(ui.proxyInput.style.transform, 'translate(55px, 110px)');
assert.strictEqual(ui.proxyInput.style.fontSize, '14px');
assert.strictEqual(ui.proxyInput.style.opacity, '0'); // because value is empty

// Test with value
ui.proxyInput.value = 'hello';
ui.alignWithCursor(mockTerm);
assert.strictEqual(ui.proxyInput.style.opacity, '1');
assert.strictEqual(ui.proxyInput.style.width, 'calc(100vw - 55px - 20px)');

console.log("All unit tests passed. Alignment verified.");
