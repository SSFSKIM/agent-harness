import type { HooksMap, HookEvent, HookCallbackMatcher } from "./types.js";

/** Fold builder fragments into one HooksMap, concatenating matcher arrays per event. */
export function mergeHooks(...fragments: HooksMap[]): HooksMap {
  const out: HooksMap = {};
  for (const frag of fragments) {
    for (const key of Object.keys(frag) as HookEvent[]) {
      const matchers = frag[key];
      if (!matchers?.length) continue;
      (out[key] ??= [] as HookCallbackMatcher[]).push(...matchers);
    }
  }
  return out;
}
