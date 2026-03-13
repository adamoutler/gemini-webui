const assert = require('assert');

class MobileInputBuffer {
  constructor(emitCallback, isMobile) {
    this.emitCallback = emitCallback;
    this.isMobile = isMobile;
  }

  handleInput(e, isComposing, value) {
    if (e.inputType === 'deleteContentBackward') {
        if (!this.isMobile) return undefined;
        this.emitCallback('\x7f');
        return undefined;
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

let emitted = [];
let buffer = new MobileInputBuffer((data) => emitted.push(data), true); 

buffer.handleKeyDown({key: 'Backspace', preventDefault: () => {}}, '');
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], '\x7f');
emitted = [];

let newValue = buffer.handleInput({data: ' '}, false, 'hello ');
assert.strictEqual(newValue, '');
assert.strictEqual(emitted.length, 1);
assert.strictEqual(emitted[0], 'hello ');
emitted = [];

newValue = buffer.handleInput({data: 'x'}, true, 'x');
assert.strictEqual(newValue, undefined); 
assert.strictEqual(emitted.length, 0);

console.log("All unit tests passed.");