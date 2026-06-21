import { describe, it, expect } from "vitest";
import { z } from "zod";
import { dynamicToolId, jsonSchemaToZodShape } from "../../src/broker.js";

describe("dynamicToolId", () => {
  it("namespaces under the cc-dyn in-process server", () => {
    expect(dynamicToolId("linear_graphql")).toBe("mcp__cc-dyn__linear_graphql");
  });
});

describe("jsonSchemaToZodShape", () => {
  it("maps the linear_graphql schema: required string + optional nullable object", () => {
    const shape = jsonSchemaToZodShape({
      type: "object",
      required: ["query"],
      properties: {
        query: { type: "string", description: "GraphQL document." },
        variables: { type: ["object", "null"], additionalProperties: true },
      },
    });
    expect(Object.keys(shape).sort()).toEqual(["query", "variables"]);
    expect(shape.query).toBeInstanceOf(z.ZodString);                 // required -> not optional
    expect(shape.variables).toBeInstanceOf(z.ZodOptional);           // not in required -> optional
    // required field accepts a string and rejects a number
    expect(shape.query.safeParse("hi").success).toBe(true);
    expect(shape.query.safeParse(123).success).toBe(false);
    // optional field accepts undefined AND null (the "null" member of the type union)
    expect(shape.variables.safeParse(undefined).success).toBe(true);
    expect(shape.variables.safeParse(null).success).toBe(true);
    expect(shape.variables.safeParse({ a: 1 }).success).toBe(true);
  });

  it("maps a string enum to z.enum (status-style fields)", () => {
    const shape = jsonSchemaToZodShape({ type: "object", required: ["status"], properties: { status: { type: "string", enum: ["done", "blocked", "needs_human"] } } });
    expect(shape.status.safeParse("done").success).toBe(true);
    expect(shape.status.safeParse("nope").success).toBe(false);
  });

  it("maps array/number/boolean and is lenient on missing/odd nodes", () => {
    const shape = jsonSchemaToZodShape({
      type: "object",
      properties: {
        ids: { type: "array", items: { type: "string" } },
        n: { type: "integer" },
        ok: { type: "boolean" },
        weird: { type: "banana" },
      },
    });
    expect(shape.ids.safeParse(["a", "b"]).success).toBe(true);
    expect(shape.ids.safeParse([1]).success).toBe(false);
    expect(shape.n.safeParse(3).success).toBe(true);
    expect(shape.ok.safeParse(true).success).toBe(true);
    expect(shape.weird.safeParse({ anything: 1 }).success).toBe(true);   // unknown type -> z.any()
  });

  it("returns an empty shape for a schema without properties", () => {
    expect(jsonSchemaToZodShape({ type: "object" })).toEqual({});
    expect(jsonSchemaToZodShape(undefined)).toEqual({});
  });
});
