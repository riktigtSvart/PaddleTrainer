// Compile only the small frontend units under test using the project's own TypeScript.
// Node's test runner needs no extra package or generated files in the repository.
import ts from "typescript";
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const native = createRequire(import.meta.url);
const cache = new Map();
export function load(relative) {
  const base = resolve(root, relative);
  const filename = existsSync(base)
    ? base
    : existsSync(base + ".ts")
      ? base + ".ts"
      : base + ".tsx";
  if (cache.has(filename)) return cache.get(filename).exports;
  const unit = { exports: {} };
  cache.set(filename, unit);
  const source = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  function require(name) {
    if (name.startsWith("@/")) return load("src/" + name.slice(2));
    if (name.startsWith(".")) return load(resolve(dirname(filename), name));
    return native(name);
  }
  new Function("require", "module", "exports", source)(
    require,
    unit,
    unit.exports,
  );
  return unit.exports;
}
