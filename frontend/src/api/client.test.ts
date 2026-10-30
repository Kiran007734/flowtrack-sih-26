import { afterEach, describe, expect, it, vi } from "vitest";
import { api, setAccessToken } from "@/api/client";

describe("API client problem responses", () => {
  afterEach(() => {
    setAccessToken(null);
    vi.unstubAllGlobals();
  });

  it("parses RFC 7807 application/problem+json errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: "Invalid email or password",
      code: "authentication_required",
    }), {
      status: 401,
      headers: { "content-type": "application/problem+json" },
    })));

    await expect(api.login("person@example.org", "synthetic-password")).rejects.toMatchObject({
      message: "Invalid email or password",
      status: 401,
      code: "authentication_required",
    });
  });
});
