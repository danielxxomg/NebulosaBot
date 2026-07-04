import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { createElement } from "react";

import Loading from "@/app/(authenticated)/loading";
import AuthenticatedError from "@/app/(authenticated)/error";

describe("Authenticated loading boundary", () => {
  it("renders a skeleton shell with multiple skeleton placeholders", () => {
    const { container } = render(createElement(Loading));

    const skeletons = container.querySelectorAll('[data-slot="skeleton"]');

    // A real loading shell must render several skeleton nodes (sidebar +
    // content area). Asserting >1 proves the component actually rendered its
    // placeholder structure rather than returning an empty tree.
    expect(skeletons.length).toBeGreaterThan(1);
  });
});

describe("Authenticated error boundary", () => {
  it("renders the error message and retries rendering via the reset button", () => {
    const reset = vi.fn();
    const error = new Error("boom");

    render(createElement(AuthenticatedError, { error, reset }));

    // Behavioral: the recovery UI surfaces a clear title plus the thrown
    // error's message, then retries rendering when the user clicks reset.
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();

    fireEvent.click(screen.getByRole("button"));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
