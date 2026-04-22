const assert = require("assert");

// Mock DOM with Event Dispatching
class MockElement {
  constructor(tag, id) {
    this.tagName = tag;
    this.id = id;
    this.classes = [];
    this.listeners = {};
    this.style = { setProperty: function () {}, cssText: "" };
    this.value = "";
    this.classList = {
      add: (cls) => {
        this.classes.push(cls);
      },
      remove: (cls) => {
        this.classes = this.classes.filter((c) => c !== cls);
      },
      contains: (cls) => {
        return this.classes.includes(cls);
      },
    };
  }

  setAttribute(k, v) {
    this[k] = v;
  }

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
  cloneNode() {
    let cloned = new MockElement(this.tagName, this.id);
    cloned.classes = [...this.classes];
    cloned.parentNode = this.parentNode;
    return cloned;
  }
}

let mockCtrlBtn = new MockElement("button", "ctrl-toggle");
let mockAltBtn = new MockElement("button", "alt-toggle");

const mockParent = {
  replaceChild: function (newChild, oldChild) {
    if (oldChild === mockCtrlBtn) mockCtrlBtn = newChild;
    if (oldChild === mockAltBtn) mockAltBtn = newChild;
  },
};

mockCtrlBtn.parentNode = mockParent;
mockAltBtn.parentNode = mockParent;

global.document = {
  body: {
    children: [],
    appendChild: function (child) {
      this.children.push(child);
    },
  },
  getElementById: function (id) {
    if (id === "ctrl-toggle") return mockCtrlBtn;
    if (id === "alt-toggle") return mockAltBtn;
    return null;
  },
  createElement: function (tag) {
    return new MockElement(tag, "");
  },
  querySelector: function (sel) {
    return new MockElement("input", "");
  },
};

global.window = {
  matchMedia: function (q) {
    return { matches: true };
  },
};

const {
  MobileInputBuffer,
  MobileInputUI,
  MobileTerminalController,
  MobileModifierState,
} = require("../../src/static/mobile_input.js");

let emitted = [];
let modifierState = new MobileModifierState();
let bufferWithMod = new MobileInputBuffer(
  (data) => emitted.push(data),
  true,
  modifierState,
);

// Simulate "tap Ctrl" -> "tap c" sequence
let preventDefaultCalled = false;
mockCtrlBtn.dispatchEvent({
  type: "touchstart",
  preventDefault: () => {
    preventDefaultCalled = true;
  },
});
mockCtrlBtn.dispatchEvent({
  type: "touchend",
  preventDefault: () => {},
});

assert.strictEqual(preventDefaultCalled, true);
assert.strictEqual(modifierState.ctrlActive, true);
assert.ok(mockCtrlBtn.classes.includes("active"));

// Tap c
let inputRet = bufferWithMod.handleInput({ data: "c" }, false, "c");
assert.strictEqual(inputRet, ""); // buffer cleared
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], "\x03"); // \x03 emitted
assert.strictEqual(modifierState.ctrlActive, false); // state cleared
assert.strictEqual(mockCtrlBtn.classes.includes("active"), false); // active class removed

console.log(
  "All unit tests passed. Modifier State Machine verified with full Event Sequence.",
);
