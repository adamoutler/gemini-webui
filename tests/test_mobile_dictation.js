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
}

global.document = {
  body: {
    children: [],
    appendChild: function (child) {
      this.children.push(child);
    },
  },
  createElement: function (tag) {
    return new MockElement(tag, "");
  },
};

const {
  MobileInputBuffer,
  MobileInputUI,
} = require("../src/static/mobile_input.js");

let emitted = [];
let buffer = new MobileInputBuffer((data) => emitted.push(data), true, null);
let ui = new MobileInputUI(
  "test",
  buffer.handleInput.bind(buffer),
  buffer.handleKeyDown.bind(buffer),
);

// Test Dictation heuristics without spaces so it doesn't instantly flush
ui.proxyInput.value = "helloWorldNoSpaces";
console.log("Dispatching event...");
console.log("Dispatching event...");
console.log("Dispatching event...");
console.log("Dispatching event...");
console.log("Dispatching event...");
ui.proxyInput.dispatchEvent({
  type: "input",
  inputType: "insertDictationResult",
  data: "helloWorldNoSpaces",
});

// Should expand visually immediately
console.log("width:", ui.proxyInput.style.width);
console.log("width:", ui.proxyInput.style.width);
console.log("width:", ui.proxyInput.style.width);
console.log("width:", ui.proxyInput.style.width);
console.log("width:", ui.proxyInput.style.width);
assert.strictEqual(ui.proxyInput.style.width, "calc(100vw - 20px)");
assert.strictEqual(ui.proxyInput.style.left, "10px");

// Timer should commit after 800ms
assert.strictEqual(emitted.length, 0); // Not committed yet

assert.ok(ui.dictationTimer);

// Manually trigger the timer callback
clearTimeout(ui.dictationTimer);
buffer.handleInput({ data: " " }, false, ui.proxyInput.value + " ");
ui.proxyInput.value = "";

assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], "helloWorldNoSpaces ");
assert.strictEqual(ui.proxyInput.value, "");

console.log("Dictation detection and auto-commit heuristics verified.");
