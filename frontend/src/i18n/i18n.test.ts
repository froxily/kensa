import { describe, expect, it } from "vitest";

import { CATALOG } from "./catalog";
import { en } from "./en";
import { LOCALES } from "./messages";

interface Tree {
  readonly [key: string]: string | Tree;
}

function leaves(tree: Tree, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.set(path, value);
    else for (const [k, v] of leaves(value, path)) out.set(k, v);
  }
  return out;
}

const placeholders = (text: string) =>
  [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();

// Strings that are the same in every language: names, and each language named in itself.
const SAME_IN_EVERY_LOCALE = new Set([
  "app.name",
  "language.en",
  "language.ja",
  "health.pgvector",
  "categories.docker",
]);

describe("locale catalogs", () => {
  const english = leaves(en);

  it.each(LOCALES)("%s has every English key, non-empty, with the same placeholders", (locale) => {
    const strings = leaves(CATALOG[locale]);
    expect([...strings.keys()]).toEqual([...english.keys()]);
    for (const [key, text] of strings) {
      expect(text.trim(), key).not.toBe("");
      expect(placeholders(text), key).toEqual(placeholders(english.get(key) ?? ""));
    }
  });

  it("translates every Japanese string except names", () => {
    const untranslated = [...leaves(CATALOG.ja)].filter(
      ([key, text]) => !SAME_IN_EVERY_LOCALE.has(key) && text === english.get(key),
    );
    expect(untranslated.map(([key]) => key)).toEqual([]);
  });

  // A file written in a legacy code page turns every non-ASCII character into "?" (v1.1).
  it.each(LOCALES)("%s has no characters lost to an encoding", (locale) => {
    const damaged = [...leaves(CATALOG[locale])].filter(
      ([, text]) => /\?\?|�|^\?+$/.test(text) || text.startsWith("﻿"),
    );
    expect(damaged.map(([key]) => key)).toEqual([]);
  });

  it("writes every Japanese string except names in Japanese script", () => {
    const latinOnly = [...leaves(CATALOG.ja)].filter(
      ([key, text]) => !SAME_IN_EVERY_LOCALE.has(key) && !/[぀-ヿ一-鿿]/.test(text),
    );
    expect(latinOnly.map(([key]) => key)).toEqual([]);
  });
});
