import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { CATALOG } from "../i18n/catalog";
import { readLocale } from "../i18n/preference";
import { health, mockApi } from "../test/mockApi";
import { renderApp } from "../test/render";

describe("app shell", () => {
  beforeEach(() => {
    mockApi({
      "GET /api/health": { body: health() },
      "GET /api/investigations": { body: { items: [], total: 0 } },
    });
  });

  it("renders navigation, skip link and the overview empty state", async () => {
    renderApp("/");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main",
    );
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    expect(await screen.findByText("No investigations yet")).toBeInTheDocument();
  });

  it("shows a not-found page with a way back", async () => {
    const user = userEvent.setup();
    renderApp("/does-not-exist");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to overview" }));
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
  });

  it("switches to dark mode and remembers the choice", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.selectOptions(screen.getByLabelText("Theme"), "dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("kensa.theme")).toBe("dark");
    await user.selectOptions(screen.getByLabelText("Theme"), "light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("switches to Japanese, marks the page language and remembers the choice", async () => {
    const user = userEvent.setup();
    const ja = CATALOG.ja;
    renderApp("/");
    expect(document.documentElement).toHaveAttribute("lang", "en");
    await user.selectOptions(screen.getByLabelText("Language"), "ja");
    expect(document.documentElement).toHaveAttribute("lang", "ja");
    expect(window.localStorage.getItem("kensa.locale")).toBe("ja");
    expect(screen.getByRole("navigation", { name: ja.nav.label })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: ja.overview.title })).toBeInTheDocument();
    expect(screen.getByLabelText(ja.language.label)).toHaveValue("ja");
  });

  it("starts in the language chosen last time, and ignores an unknown one", () => {
    window.localStorage.setItem("kensa.locale", "ja");
    expect(readLocale()).toBe("ja");
    window.localStorage.setItem("kensa.locale", "fr");
    expect(readLocale()).toBe("en");
  });
});
