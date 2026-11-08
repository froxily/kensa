const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");

test("basename is retained", () => assert.equal(path.basename("a/b"), "b"));
test("extension is retained", () => assert.equal(path.extname("a.json"), ".json"));
test("path join is stable", () => assert.equal(path.join("a", "b"), "a/b"));
test("label is nonempty", () => assert.ok("iris".length > 0));
test("prefix matches", () => assert.ok("iris".startsWith("ir")));

test("reads runtime settings", () => {
  const settings = JSON.parse(readFileSync("config/runtime.json", "utf8"));
  assert.equal(settings.enabled, true);
});
