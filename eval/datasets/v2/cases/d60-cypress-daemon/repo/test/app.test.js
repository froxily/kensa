const test = require("node:test");
const assert = require("node:assert/strict");
const { add } = require("../src/app");

test("adds zero", () => assert.equal(add(2, 0), 2));
test("adds one", () => assert.equal(add(2, 1), 3));
test("adds two", () => assert.equal(add(2, 2), 4));
test("adds three", () => assert.equal(add(2, 3), 5));
test("adds four", () => assert.equal(add(2, 4), 6));
test("adds five", () => assert.equal(add(2, 5), 7));
test("adds six", () => assert.equal(add(2, 6), 8));
test("adds seven", () => assert.equal(add(2, 7), 9));
