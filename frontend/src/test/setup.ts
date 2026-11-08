import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { FakeEventSource } from "./mockApi";

// jsdom does not implement scrolling.
Element.prototype.scrollIntoView = vi.fn();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  FakeEventSource.instances = [];
  window.localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.lang = "";
});
