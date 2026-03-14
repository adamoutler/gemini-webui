with open("tests/test_mobile_dictation.js", "r") as f:
    c = f.read()
c = c.replace("ui.proxyInput.dispatchEvent({", "console.log('Dispatching event...');\nui.proxyInput.dispatchEvent({")
c = c.replace("assert.strictEqual(ui.proxyInput.style.width", "console.log('width:', ui.proxyInput.style.width);\nassert.strictEqual(ui.proxyInput.style.width")
with open("tests/test_mobile_dictation.js", "w") as f:
    f.write(c)
