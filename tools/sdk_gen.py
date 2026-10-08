"""Generate the SDKs' typed layer from the /v1 contract (docs/openapi-v1.json).

    python tools/sdk_gen.py godot            # writes sdk/godot/addons/thespis/api.gd
    python tools/sdk_gen.py unity            # writes sdk/unity/com.thespis.client/Runtime/Core/Api.g.cs
    python tools/sdk_gen.py all --check      # fails if a committed file isn't what the spec makes

What's generated is the part that must match the server exactly: one class per schema, with typed fields, and the
table of routes (method, path, request and reply types). The engine-idiomatic API around it is written by hand, so
the routes and fields can't drift from the server's while the calls read the way each engine's code reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "openapi-v1.json"
GODOT_OUT = ROOT / "sdk" / "godot" / "addons" / "thespis" / "api.gd"
UNITY_OUT = ROOT / "sdk" / "unity" / "com.thespis.client" / "Runtime" / "Core" / "Api.g.cs"
SKIP = {"HTTPValidationError", "ValidationError"}

# GDScript words a JSON field can't be named as; such a field gets a trailing underscore (ObserveIn's `true`).
GD_RESERVED = {"and", "as", "assert", "await", "break", "breakpoint", "class", "class_name", "const", "continue",
               "elif", "else", "enum", "extends", "false", "for", "func", "if", "in", "is", "match", "namespace",
               "not", "null", "or", "pass", "preload", "return", "self", "signal", "static", "super", "trait",
               "true", "var", "void", "when", "while", "yield", "PI", "TAU", "INF", "NAN"}


def _ref(schema: dict) -> str | None:
    r = schema.get("$ref")
    return r.rsplit("/", 1)[1] if r else None


def _unwrap(schema: dict) -> tuple[dict, bool]:
    """A field's schema without its `| null`, and whether it may be null."""
    options = schema.get("anyOf")
    if not options:
        return schema, False
    real = [o for o in options if o.get("type") != "null"]
    return (real[0] if len(real) == 1 else {}), len(real) < len(options)


def route_name(operation_id: str) -> str:
    return operation_id.split("_v1_", 1)[0]


def routes(spec: dict) -> list[tuple[str, str, str, str, str]]:
    """Each route: (name, METHOD, path, request schema or "", reply schema or ""). A list's reply is its items'."""
    out = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            reply = ""
            for code, r in op["responses"].items():
                if code.startswith("2"):
                    sch = r.get("content", {}).get("application/json", {}).get("schema", {})
                    reply = _ref(sch) or _ref(sch.get("items", {})) or ""
            out.append((route_name(op["operationId"]), method.upper(), path, _ref(body) or "", reply))
    return out


# ---------------------------------------------------------------------------------------------------- Godot

_GD_SCALAR = {"string": ("String", '""', "str({v})"), "integer": ("int", "0", "int({v})"),
              "number": ("float", "0.0", "float({v})"), "boolean": ("bool", "false", "bool({v})"),
              "object": ("Dictionary", "{}", "{v}"), "array": ("Array", "[]", "{v}")}


def _gd_field(name: str, schema: dict) -> tuple[str, str, str, str]:
    """(declaration, read statement, write expression, doc) for one field of a generated class."""
    var = name + "_" if name in GD_RESERVED else name
    inner, nullable = _unwrap(schema)
    doc = schema.get("description") or inner.get("description") or ""
    ref = _ref(inner)
    src = f'd["{name}"]'
    if ref:
        decl = f"var {var}: {ref} = null"
        read = f'{var} = {ref}.new().read({src}) if d.get("{name}") != null else null'
        write = f"{var}.to_dict()"
        return decl, read, write, doc
    kind = inner.get("type", "")
    if nullable or kind not in _GD_SCALAR:
        what = kind or "any"
        decl = f"var {var} = null"
        doc = f"{what}, or null" + (f". {doc}" if doc else "")
        cast = _GD_SCALAR.get(kind, ("", "", "{v}"))[2]
        read = f'{var} = {cast.format(v=src)} if d.get("{name}") != null else null' if kind in _GD_SCALAR else \
            f'{var} = d.get("{name}")'
        return decl, read, var, doc
    typ, zero, cast = _GD_SCALAR[kind]
    default = schema.get("default", inner.get("default"))
    if default is not None and kind in ("string", "integer", "number", "boolean"):
        zero = json.dumps(default) if kind != "number" else repr(float(default))
    if kind == "array":
        items = inner.get("items", {})
        item_ref = _ref(items)
        item_kind = items.get("type")
        if item_ref:
            typ = f"Array[{item_ref}]"
            read = f'{var}.assign(d.get("{name}", []).map(func(x): return {item_ref}.new().read(x)))'
            write = f"{var}.map(func(x): return x.to_dict())"
            return f"var {var}: {typ} = []", read, write, doc
        if item_kind in ("string", "integer", "number", "boolean"):
            item_typ, _, item_cast = _GD_SCALAR[item_kind]
            typ = f"Array[{item_typ}]"
            read = f'{var}.assign(d.get("{name}", []).map(func(x): return {item_cast.format(v="x")}))'
            return f"var {var}: {typ} = []", read, var, doc
        return f"var {var}: Array = []", f'{var} = d.get("{name}", [])', var, doc
    read = f'if d.has("{name}"): {var} = {cast.format(v=src)}'
    return f"var {var}: {typ} = {zero}", read, var, doc


def godot(spec: dict) -> str:
    out = [
        "## Generated by tools/sdk_gen.py from docs/openapi-v1.json: don't edit it; change the server, then regenerate.",
        "##",
        "## The /v1 contract in GDScript: a class per schema, with typed fields, and the route table the client calls",
        "## through. Each class reads itself from a reply (`read`, whole numbers back to int, as GDScript's JSON makes",
        "## every number a float) and writes itself as a request body (`to_dict`, leaving out what's null).",
        "class_name ThespisApi",
        "extends RefCounted",
        "",
        f'const VERSION := "{spec["info"]["version"]}"',
        "",
        "## Each route: [method, path, request class name or \"\", reply class name or \"\"]. Paths keep their {params}.",
        "const ROUTES := {",
    ]
    for name, method, path, body, reply in routes(spec):
        out.append(f'\t"{name}": ["{method}", "{path}", "{body}", "{reply}"],')
    out.append("}")
    names = [n for n in spec["components"]["schemas"] if n not in SKIP]
    out += ["", "", "## A new, empty instance of the class with this name, or null.", "static func make(name: String):",
            "\tmatch name:"]
    out += [f'\t\t"{n}":\n\t\t\treturn {n}.new()' for n in names]
    out.append("\treturn null")
    for name, schema in spec["components"]["schemas"].items():
        if name in SKIP:
            continue
        out += ["", ""]
        if schema.get("description"):
            out.append(f"## {schema['description'].splitlines()[0]}")
        out.append(f"class {name} extends RefCounted:")
        fields = [(k, _gd_field(k, v)) for k, v in schema.get("properties", {}).items()]
        for _, (decl, _, _, doc) in fields:
            out.append(f"\t{decl}" + (f"  ## {doc}" if doc else ""))
        out += ["", "\tfunc read(d: Dictionary):"]
        out += [f"\t\t{read}" for _, (_, read, _, _) in fields] or ["\t\tpass"]
        out += ["\t\treturn self", "", "\tfunc to_dict() -> Dictionary:", "\t\tvar d := {}"]
        for key, (decl, _, write, _) in fields:
            var = decl.split()[1].rstrip(":")
            maybe = decl.endswith("= null")  # a typed String or int can't be compared with null in GDScript
            out.append(f'\t\tif {var} != null: d["{key}"] = {write}' if maybe else f'\t\td["{key}"] = {write}')
        out.append("\t\treturn d")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------- Unity (C#)

_CS_SCALAR = {"string": "string", "integer": "int", "number": "double", "boolean": "bool"}


def _pascal(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))


def _cs_type(schema: dict) -> str:
    """A schema's C# type, without nullability."""
    ref = _ref(schema)
    if ref:
        return ref
    kind = schema.get("type")
    if kind in _CS_SCALAR:
        return _CS_SCALAR[kind]
    if kind == "array":
        return f"List<{_cs_type(schema.get('items', {}))}>"
    if kind == "object" or "additionalProperties" in schema:
        extra = schema.get("additionalProperties", True)
        if not isinstance(extra, dict):
            return "JObject"
        if "anyOf" in extra:  # one of several scalars: a choice's bindings, a template's fill
            return "Dictionary<string, object>"
        return f"Dictionary<string, {_cs_type(extra)}>"
    return "JToken"


def _cs_field(name: str, schema: dict) -> list[str]:
    inner, nullable = _unwrap(schema)
    typ = _cs_type(inner)
    doc = schema.get("description") or inner.get("description") or ""
    lines = [f"        /// <summary>{doc}</summary>"] if doc else []
    if nullable:
        lines.append(f'        [JsonProperty("{name}", NullValueHandling = NullValueHandling.Ignore)]')
        lines.append(f"        public {typ}? {_pascal(name)} {{ get; set; }}")
        return lines
    default = schema.get("default", inner.get("default"))
    if default is not None and typ in ("string", "int", "bool"):
        init = json.dumps(default)
    elif default is not None and typ == "double":
        init = repr(float(default))
    elif typ == "string":
        init = '""'
    elif typ in ("int", "double", "bool"):
        init = ""
    else:
        init = "new()"
    lines.append(f'        [JsonProperty("{name}")]')
    lines.append(f"        public {typ} {_pascal(name)} {{ get; set; }}" + (f" = {init};" if init else ""))
    return lines


def unity(spec: dict) -> str:
    out = [
        "// Generated by tools/sdk_gen.py from docs/openapi-v1.json: don't edit it; change the server, then regenerate.",
        "//",
        "// The /v1 contract in C#: a class per schema, with typed properties named as C# names them and serialised as",
        "// the server names them, and the route table the client calls through. Nothing here touches UnityEngine, so",
        "// it builds under plain .NET as well (netstandard2.1, C# 9).",
        "#nullable enable",
        "using System.Collections.Generic;",
        "using Newtonsoft.Json;",
        "using Newtonsoft.Json.Linq;",
        "",
        "namespace Thespis.Api",
        "{",
        "    /// <summary>A /v1 route: its method and path (with {params}), and its request and reply schemas.</summary>",
        "    public sealed class Route",
        "    {",
        "        public string Method { get; }",
        "        public string Path { get; }",
        "        public string Request { get; }",
        "        public string Reply { get; }",
        "",
        "        public Route(string method, string path, string request, string reply)",
        "        {",
        "            Method = method;",
        "            Path = path;",
        "            Request = request;",
        "            Reply = reply;",
        "        }",
        "    }",
        "",
        "    public static class Routes",
        "    {",
        f'        public const string Version = "{spec["info"]["version"]}";',
    ]
    for name, method, path, body, reply in routes(spec):
        out.append(f'        public static readonly Route {_pascal(name)} = new Route("{method}", "{path}", "{body}", '
                   f'"{reply}");')
    out.append("    }")
    for name, schema in spec["components"]["schemas"].items():
        if name in SKIP:
            continue
        out.append("")
        if schema.get("description"):
            out.append(f"    /// <summary>{schema['description'].splitlines()[0]}</summary>")
        out += [f"    public class {name}", "    {"]
        fields = [_cs_field(k, v) for k, v in schema.get("properties", {}).items()]
        for i, lines in enumerate(fields):
            out += ([""] if i else []) + lines
        out.append("    }")
    out.append("}")
    return "\n".join(out) + "\n"


TARGETS = {"godot": (godot, GODOT_OUT), "unity": (unity, UNITY_OUT)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=[*TARGETS, "all"])
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs from the spec's")
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    stale = 0
    for target in TARGETS if args.target == "all" else [args.target]:
        make, out = TARGETS[target]
        text = make(spec)
        if args.check:
            current = out.read_text(encoding="utf-8") if out.exists() else ""
            if current != text:
                print(f"{out.relative_to(ROOT)} is stale: python tools/sdk_gen.py {target}", file=sys.stderr)
                stale = 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode())
        print(f"wrote {out.relative_to(ROOT)}")
    return stale


if __name__ == "__main__":
    raise SystemExit(main())
