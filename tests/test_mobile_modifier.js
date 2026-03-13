const assert = require('assert');

// Mock DOM
global.document = {
  body: {
    appendChild: function(child) {
      this.children = this.children || [];
      this.children.push(child);
    }
  },
  getElementById: function(id) {
    return {
      tagName: 'button',
      id: id,
      classList: {
        add: function(cls) { this.classes = this.classes || []; this.classes.push(cls); },
        remove: function(cls) { if(this.classes) this.classes = this.classes.filter(c => c !== cls); },
        contains: function(cls) { return this.classes && this.classes.includes(cls); }
      },
      addEventListener: function(evt, cb) {}
    };
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
    return { matches: true }; 
  }
};

const { MobileInputBuffer, MobileInputUI, MobileTerminalController, MobileModifierState } = require('../src/static/mobile_input.js');

let emitted = [];

// Test Modifier State Machine directly
let modifierState = new MobileModifierState();

// Turn on Ctrl
modifierState.toggleCtrl(true);
assert.strictEqual(modifierState.ctrlActive, true);
let modData = modifierState.applyModifiers('c');
assert.strictEqual(modData, '\x03'); // 'c' is 99, 99-96 = 3 -> \x03
assert.strictEqual(modifierState.ctrlActive, false); // auto-cleared

// Turn on Alt
modifierState.toggleAlt(true);
assert.strictEqual(modifierState.altActive, true);
modData = modifierState.applyModifiers('b');
assert.strictEqual(modData, '\x1bb'); // Alt+b
assert.strictEqual(modifierState.altActive, false);

// Test MobileInputBuffer integration with modifier
let bufferWithMod = new MobileInputBuffer((data) => emitted.push(data), true, modifierState);

modifierState.toggleCtrl(true);
let inputRet = bufferWithMod.handleInput({data: 'c'}, false, 'c');
assert.strictEqual(inputRet, ''); // buffer cleared
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], '\x03'); // emit directly to terminal!
assert.strictEqual(modifierState.ctrlActive, false); // state cleared
emitted = [];

console.log("All unit tests passed. Modifier State Machine verified.");