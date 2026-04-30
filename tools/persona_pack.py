from __future__ import annotations

import argparse
import io
import shutil
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERSONAS_ROOT = PROJECT_ROOT / "personas"
REQUIRED_SYSTEM_FILES = ("system.jinja2", "system_prompt.md")


class ValidationResult(NamedTuple):
    ok: bool
    errors: list[str]


def validate_zip(zip_path: Path) -> ValidationResult:
    """Check that a .persona zip has required structure and valid persona.yaml."""
    errors: list[str] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())

            if "persona.yaml" not in names:
                errors.append("Missing persona.yaml")
            else:
                try:
                    meta = yaml.safe_load(zf.read("persona.yaml").decode("utf-8"))
                    if not meta or not isinstance(meta, dict):
                        errors.append("persona.yaml is empty or not a mapping")
                    elif not (meta.get("name") or meta.get("wake_word")):
                        errors.append("persona.yaml must have 'name' or 'wake_word' field")
                except yaml.YAMLError as exc:
                    errors.append(f"persona.yaml parse error: {exc}")

            if not any(f in names for f in REQUIRED_SYSTEM_FILES):
                errors.append(
                    f"Missing system prompt ({' or '.join(REQUIRED_SYSTEM_FILES)})"
                )
    except zipfile.BadZipFile as exc:
        errors.append(f"Not a valid zip file: {exc}")

    return ValidationResult(ok=len(errors) == 0, errors=errors)


def pack(persona_dir: Path, output: Path | None = None) -> Path:
    """Pack a persona directory into a .persona zip file."""
    persona_dir = Path(persona_dir).resolve()
    if not persona_dir.is_dir():
        raise FileNotFoundError(f"Persona directory not found: {persona_dir}")

    persona_name = persona_dir.name
    if output is None:
        output = Path(f"{persona_name}.persona")
    output = Path(output)

    needs_auto_yaml = not (persona_dir / "persona.yaml").exists()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if needs_auto_yaml:
            auto_meta = yaml.dump(
                {"name": persona_name, "wake_word": persona_name},
                allow_unicode=True,
            )
            zf.writestr("persona.yaml", auto_meta)

        for item in sorted(persona_dir.rglob("*")):
            if item.is_file():
                arcname = str(item.relative_to(persona_dir))
                zf.write(item, arcname)

    return output


def export(persona_dir: Path, output: Path | None = None) -> Path:
    """Alias for pack."""
    return pack(persona_dir, output)


def install(zip_path: Path, target: Path | None = None, force: bool = False) -> Path:
    """Validate and extract a .persona zip into the personas directory."""
    zip_path = Path(zip_path).resolve()
    if not zip_path.exists():
        raise FileNotFoundError(f"Pack file not found: {zip_path}")

    result = validate_zip(zip_path)
    if not result.ok:
        msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in result.errors)
        raise ValueError(msg)

    # Determine install directory name from zip stem
    persona_name = zip_path.stem

    install_root = Path(target) if target is not None else PERSONAS_ROOT
    install_dir = install_root / persona_name

    if install_dir.exists() and not force:
        raise FileExistsError(
            f"Target already exists: {install_dir}. Use --force to overwrite."
        )
    if install_dir.exists():
        shutil.rmtree(install_dir)

    install_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(install_dir)

    return install_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_pack(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    out = pack(Path(args.persona_dir), output)
    print(out)
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    target = Path(args.target) if args.target else None
    try:
        out = install(Path(args.zip_path), target=target, force=args.force)
        print(out)
        return 0
    except (FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    result = validate_zip(Path(args.zip_path))
    if result.ok:
        print("OK")
        return 0
    for err in result.errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


def _cmd_export(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    out = export(Path(args.persona_dir), output)
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="persona_pack",
        description="Pack, install, and validate .persona zip files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_pack = sub.add_parser("pack", help="Pack a persona directory into a .persona zip")
    p_pack.add_argument("persona_dir", help="Path to persona directory")
    p_pack.add_argument("--output", "-o", help="Output file path (default: <name>.persona)")

    p_install = sub.add_parser("install", help="Install a .persona zip into personas/")
    p_install.add_argument("zip_path", help="Path to .persona zip file")
    p_install.add_argument("--target", "-t", help="Install root directory (default: personas/)")
    p_install.add_argument("--force", "-f", action="store_true", help="Overwrite if exists")

    p_validate = sub.add_parser("validate", help="Validate a .persona zip")
    p_validate.add_argument("zip_path", help="Path to .persona zip file")

    p_export = sub.add_parser("export", help="Export (alias for pack)")
    p_export.add_argument("persona_dir", help="Path to persona directory")
    p_export.add_argument("--output", "-o", help="Output file path (default: <name>.persona)")

    args = parser.parse_args(argv)
    dispatch = {
        "pack": _cmd_pack,
        "install": _cmd_install,
        "validate": _cmd_validate,
        "export": _cmd_export,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
