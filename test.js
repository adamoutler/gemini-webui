const fs = require("fs");
const code = fs.readFileSync("src/static/js/mobile/ui.js", "utf8");
console.log(code.substring(160, 200));
