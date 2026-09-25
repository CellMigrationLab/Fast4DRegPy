"""Turn an original Fast4DReg Fiji macro into a headless ImageJ 1.x batch macro.

Only the SciJava ``#@`` parameter declarations and the Bio-Formats opener are
replaced. Every registration, projection, reslice, scale, crop and correction
command is left exactly as written in the original macro, so the patched macro
exercises the original Fiji/NanoJ code path.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Commands renamed between the NanoJ-Core update site (v1 macros) and the
# Fast4DReg jar (v2 macros). The Java implementation is the same legacy code.
V1_COMMANDS = {
    'run("Estimate Drift"': 'run("F4DR Estimate Drift"',
    'run("Correct Drift"': 'run("F4DR Correct Drift"',
    'run("Open NanoJ Table (NJT)..."': 'run("F4DR Open NanoJ Table (NJT)..."',
    'run("Save Results-Table as NJT..."': 'run("F4DR Save Results-Table as NJT..."',
}


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value))


def patch(source: str, settings: dict[str, object]) -> str:
    lines = []
    used = set()
    for line in source.splitlines():
        match = re.match(r"\s*#@\s*(\S+)\s*(?:\(.*\))?\s*(\w+)\s*;?\s*$", line)
        if match:
            kind, name = match.groups()
            if kind.lower() == "string" and "visibility" in line:
                continue  # dialog separator messages
            if name not in settings:
                raise KeyError(f"no value supplied for macro parameter {name!r}")
            value = settings[name]
            if kind.lower().startswith("file[]"):
                lines.append(f"{name} = newArray({_literal(value)});")
            else:
                lines.append(f"{name} = {_literal(value)};")
            used.add(name)
            continue
        line = line.replace('run("Bio-Formats Macro Extensions");', "")
        # "Collect Garbage" blocks forever in headless ImageJ 1.53t batch mode;
        # it only frees memory and has no effect on the image data.
        line = line.replace('run("Collect Garbage");', 'call("java.lang.System.gc");')
        line = line.replace("Ext.openImagePlus(files[p]);", "open(files[p]);")
        line = re.sub(
            r'run\("Bio-Formats", options\);',
            "open(my_file_path_for_bf);",
            line,
        )
        for old, new in V1_COMMANDS.items():
            line = line.replace(old, new)
        lines.append(line)
    unused = set(settings) - used
    if unused:
        raise KeyError(f"unused settings {sorted(unused)}")
    text = "\n".join(lines)
    # The v1/v2 Bio-Formats fallbacks open the raw file; point them at open().
    text = text.replace(
        "open(my_file_path_for_bf);",
        "open(" + ("files[p]" if "files[p]" in text else "my_file_path") + ");",
    )
    text = text.replace('showMessage("All DONE!', 'print("All DONE!')
    # In GUI mode (under Xvfb) the Log window is not echoed to stdout, so save
    # it to the path given as the macro argument; the driver waits for it.
    return (
        text
        + '\nprint("F4DR_HEADLESS_DONE");\n'
        + 'File.saveString(getInfo("log"), getArgument());\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("macro", type=Path)
    parser.add_argument("settings", type=Path, help="JSON parameter values")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    args.output.write_text(
        patch(args.macro.read_text(encoding="utf-8"), settings), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
