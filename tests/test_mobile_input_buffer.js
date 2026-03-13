const assert = require('assert');
const { MobileInputBuffer } = require('../src/static/mobile_input.js');

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

console.log("All unit tests passed.");