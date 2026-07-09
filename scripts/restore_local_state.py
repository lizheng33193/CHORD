from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path, PurePosixPath


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore a local CHORD state backup archive.")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--target-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def _default_manifest_path(archive_path: Path) -> Path:
    name = archive_path.name
    if name.endswith(".tar.gz"):
        return archive_path.with_name(name[:-7] + ".manifest.json")
    return archive_path.with_suffix(archive_path.suffix + ".manifest.json")


def _load_manifest(manifest_path: Path | None) -> dict[str, object] | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _is_unsafe_link_target(target: str) -> bool:
    link_path = PurePosixPath(target)
    return link_path.is_absolute() or any(part == ".." for part in link_path.parts)


def _safe_destination(member_name: str, *, target_root: Path) -> Path:
    member_path = PurePosixPath(member_name)
    if member_path.is_absolute():
        raise ValueError(f"unsafe archive entry (absolute path): {member_name}")
    if any(part in {"", ".."} for part in member_path.parts):
        raise ValueError(f"unsafe archive entry (path traversal): {member_name}")
    destination = target_root.joinpath(*member_path.parts)
    try:
        destination.resolve().relative_to(target_root.resolve())
    except ValueError as exc:
        raise ValueError(f"unsafe archive entry (escaped target root): {member_name}") from exc
    return destination


def main() -> int:
    args = _parse_args()
    archive_path = args.archive.resolve()
    target_root = args.target_root.resolve()
    manifest_path = args.manifest.resolve() if args.manifest else _default_manifest_path(archive_path)
    manifest = _load_manifest(manifest_path)

    if not args.dry_run:
        target_root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()

        planned: list[tuple[tarfile.TarInfo, Path]] = []
        warnings: list[str] = []
        for member in members:
            try:
                destination = _safe_destination(member.name, target_root=target_root)
            except ValueError as exc:
                print(f"error: {exc}")
                return 1
            if member.issym() or member.islnk():
                target = member.linkname or ""
                if _is_unsafe_link_target(target):
                    print(f"error: unsafe archive link target: {member.name} -> {target}")
                    return 1
                warning = f"link entry skipped: {member.name}"
                warnings.append(warning)
                print(f"warning: {warning}")
                continue
            planned.append((member, destination))

        restored = 0
        skipped = 0
        for member, destination in planned:
            if member.isdir():
                if not args.dry_run:
                    destination.mkdir(parents=True, exist_ok=True)
                restored += 1
                print(f"{'would create' if args.dry_run else 'created'} dir: {destination}")
                continue

            if not member.isfile():
                warning = f"unsupported archive entry skipped: {member.name}"
                warnings.append(warning)
                skipped += 1
                print(f"warning: {warning}")
                continue

            if destination.exists() and not args.overwrite:
                warning = f"existing file skipped: {destination}"
                warnings.append(warning)
                skipped += 1
                print(f"warning: {warning}")
                continue

            if args.dry_run:
                restored += 1
                print(f"would restore file: {destination}")
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                warning = f"empty archive member skipped: {member.name}"
                warnings.append(warning)
                skipped += 1
                print(f"warning: {warning}")
                continue
            with extracted, destination.open("wb") as handle:
                handle.write(extracted.read())
            restored += 1
            print(f"restored file: {destination}")

    print(f"restore target: {target_root}")
    print(f"mode: {'dry-run' if args.dry_run else 'apply'}")
    print(f"entries restored: {restored}")
    print(f"entries skipped: {skipped}")
    print(f"warnings: {len(warnings)}")
    if manifest is not None:
        print(f"manifest loaded: {manifest_path}")
        print(f"manifest archive sha256: {manifest.get('archive_sha256', 'unknown')}")
    print("next verification commands:")
    print("python scripts/bootstrap_runtime_dirs.py")
    print("python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
