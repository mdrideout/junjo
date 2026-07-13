#!/usr/bin/env python3
"""Generate and validate Studio production dependency license inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any


PLATFORM_ROOT = Path(__file__).resolve().parents[2]
STUDIO_ROOT = PLATFORM_ROOT / "apps/studio"
LICENSES_ROOT = STUDIO_ROOT / "licenses"
POLICY_PATH = LICENSES_ROOT / "artifact-license-policy.json"
FRONTEND_LOCK_PATH = STUDIO_ROOT / "frontend/package-lock.json"
FRONTEND_PACKAGE_PATH = STUDIO_ROOT / "frontend/package.json"
FRONTEND_INVENTORY_PATH = LICENSES_ROOT / "frontend-production.json"
INGESTION_LOCK_PATH = STUDIO_ROOT / "ingestion/Cargo.lock"
INGESTION_MANIFEST_PATH = STUDIO_ROOT / "ingestion/Cargo.toml"
INGESTION_INVENTORY_PATH = LICENSES_ROOT / "ingestion-production.json"
INVENTORY_FORMAT = "junjo.studio.dependency-license-inventory.v1"
INGESTION_TARGETS = {
    "linux/amd64": "x86_64-unknown-linux-gnu",
    "linux/arm64": "aarch64-unknown-linux-gnu",
}


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when a contract is not satisfied."""
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    """Read JSON from a repository path."""
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json(value: object) -> str:
    """Render committed inventory JSON in one deterministic format."""
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _string_list(value: object, *, owner: str) -> list[str]:
    require(isinstance(value, list), f"{owner} must be a list")
    values = value
    require(
        all(isinstance(item, str) and item for item in values),
        f"{owner} must contain non-empty strings",
    )
    require(values == sorted(set(values)), f"{owner} must be sorted and unique")
    return values


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    """Load and strictly validate the human-reviewed artifact license policy."""
    value = load_json(path)
    require(isinstance(value, dict), "artifact license policy must be an object")
    require(
        set(value) == {"schema_version", "frontend", "ingestion", "external_binaries"},
        "artifact license policy has unexpected or missing top-level fields",
    )
    require(value["schema_version"] == 1, "unsupported artifact license policy schema")

    for component in ("frontend", "ingestion"):
        section = value[component]
        require(isinstance(section, dict), f"policy {component} must be an object")
        required_fields = {"allowed_license_expressions"}
        if component == "frontend":
            required_fields.add("manual_license_overrides")
        require(
            set(section) == required_fields,
            f"policy {component} has unexpected or missing fields",
        )
        _string_list(
            section["allowed_license_expressions"],
            owner=f"policy {component} allowed_license_expressions",
        )

    overrides = value["frontend"]["manual_license_overrides"]
    require(isinstance(overrides, list), "frontend manual overrides must be a list")
    override_keys: list[tuple[str, str]] = []
    override_fields = {
        "evidence",
        "evidence_sha256",
        "license",
        "license_file",
        "name",
        "source",
        "version",
    }
    for override in overrides:
        require(isinstance(override, dict), "each frontend override must be an object")
        require(
            set(override) == override_fields,
            "frontend manual override has unexpected or missing fields",
        )
        require(
            all(
                isinstance(override[field], str) and override[field]
                for field in override
            ),
            "frontend manual override fields must be non-empty strings",
        )
        require(
            len(override["evidence_sha256"]) == 64
            and all(char in "0123456789abcdef" for char in override["evidence_sha256"]),
            "frontend override evidence_sha256 must be a lowercase SHA-256 digest",
        )
        override_keys.append((override["name"], override["version"]))
    require(
        override_keys == sorted(set(override_keys)),
        "frontend manual overrides must be sorted and unique by name/version",
    )

    external_binaries = value["external_binaries"]
    require(isinstance(external_binaries, list), "external_binaries must be a list")
    binary_keys: list[tuple[str, str]] = []
    for binary in external_binaries:
        require(isinstance(binary, dict), "each external binary must be an object")
        require(
            set(binary) == {"license", "name", "source", "version"},
            "external binary has unexpected or missing fields",
        )
        require(
            all(isinstance(binary[field], str) and binary[field] for field in binary),
            "external binary fields must be non-empty strings",
        )
        binary_keys.append((binary["name"], binary["version"]))
    require(
        binary_keys == sorted(set(binary_keys)),
        "external binaries must be sorted and unique by name/version",
    )
    return value


def _package_name(package_path: str) -> str:
    """Recover an npm package name from a package-lock packages key."""
    require(
        "node_modules/" in package_path,
        f"unexpected package-lock production path: {package_path}",
    )
    return package_path.rsplit("node_modules/", maxsplit=1)[1]


def build_frontend_inventory(
    policy: Mapping[str, Any],
    *,
    lock_path: Path = FRONTEND_LOCK_PATH,
    package_path: Path = FRONTEND_PACKAGE_PATH,
) -> dict[str, Any]:
    """Build the frontend production inventory directly from package-lock.json."""
    lock = load_json(lock_path)
    package = load_json(package_path)
    require(isinstance(lock, dict), "frontend package lock must be an object")
    require(
        lock.get("lockfileVersion") == 3, "frontend package lock must use version 3"
    )
    packages = lock.get("packages")
    require(
        isinstance(packages, dict), "frontend package lock packages must be an object"
    )
    root = packages.get("")
    require(
        isinstance(root, dict), "frontend package lock must contain its root package"
    )
    require(
        root.get("dependencies") == package.get("dependencies"),
        "frontend package.json production dependencies differ from package-lock root",
    )

    frontend_policy = policy["frontend"]
    allowed = set(frontend_policy["allowed_license_expressions"])
    overrides = {
        (override["name"], override["version"]): override
        for override in frontend_policy["manual_license_overrides"]
    }
    used_overrides: set[tuple[str, str]] = set()
    dependencies_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for dependency_path, metadata in sorted(packages.items()):
        if not dependency_path or metadata.get("dev") is True:
            continue
        require(
            isinstance(metadata, dict), f"invalid package metadata: {dependency_path}"
        )
        name = _package_name(dependency_path)
        version = metadata.get("version")
        require(
            isinstance(version, str) and version,
            f"production frontend dependency has no version: {dependency_path}",
        )
        override = overrides.get((name, version))
        declared_license = metadata.get("license")
        if declared_license is None:
            require(
                override is not None,
                f"production frontend dependency has no license or override: {name}@{version}",
            )
            license_expression = override["license"]
            license_source = "artifact-license-policy override"
            used_overrides.add((name, version))
        else:
            require(
                override is None,
                f"stale frontend license override now has package metadata: {name}@{version}",
            )
            require(
                isinstance(declared_license, str) and declared_license,
                f"invalid frontend license metadata: {name}@{version}",
            )
            license_expression = declared_license
            license_source = "package-lock.json"
        require(
            license_expression in allowed,
            f"frontend dependency has an unreviewed license expression: "
            f"{name}@{version} ({license_expression})",
        )

        entry = {
            "license": license_expression,
            "license_source": license_source,
            "name": name,
            "version": version,
        }
        identity = (name, version)
        existing_entry = dependencies_by_identity.get(identity)
        require(
            existing_entry is None or existing_entry == entry,
            f"frontend package lock gives conflicting license metadata: {name}@{version}",
        )
        dependencies_by_identity[identity] = entry

    require(
        used_overrides == set(overrides),
        "frontend policy contains an unused manual license override",
    )
    return {
        "artifact": "Studio frontend production static bundle",
        "dependencies": [
            dependencies_by_identity[identity]
            for identity in sorted(dependencies_by_identity)
        ],
        "format": INVENTORY_FORMAT,
        "scope": (
            "unique packages from package-lock v3 entries marked as part of the "
            "production dependency closure; build tools are not represented unless "
            "also production dependencies"
        ),
        "source_lock": {
            "path": "frontend/package-lock.json",
            "sha256": sha256_file(lock_path),
        },
    }


def _cargo_lock_packages(lock_path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("package")
    require(isinstance(packages, list), "Cargo.lock must contain package entries")
    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for package in packages:
        require(isinstance(package, dict), "Cargo.lock package must be an object")
        source = package.get("source")
        if source is None:
            continue
        key = (package["name"], package["version"], source)
        require(key not in indexed, f"duplicate Cargo.lock package identity: {key}")
        indexed[key] = package
    return indexed


def _cargo_metadata(target: str) -> dict[str, Any]:
    command = [
        "cargo",
        "metadata",
        "--manifest-path",
        str(INGESTION_MANIFEST_PATH),
        "--locked",
        "--format-version",
        "1",
        "--filter-platform",
        target,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    value = json.loads(result.stdout)
    require(isinstance(value, dict), "cargo metadata output must be an object")
    return value


def _normal_runtime_package_ids(metadata: Mapping[str, Any]) -> set[str]:
    resolve = metadata.get("resolve")
    require(isinstance(resolve, dict), "cargo metadata must contain a resolve graph")
    root = resolve.get("root")
    require(
        isinstance(root, str) and root, "cargo metadata must identify the root package"
    )
    nodes_value = resolve.get("nodes")
    require(
        isinstance(nodes_value, list), "cargo metadata resolve nodes must be a list"
    )
    nodes = {node["id"]: node for node in nodes_value}
    require(root in nodes, "cargo metadata resolve root has no node")

    visited = {root}
    pending = [root]
    while pending:
        node = nodes[pending.pop()]
        for dependency in node["deps"]:
            is_normal = any(
                dependency_kind["kind"] is None
                for dependency_kind in dependency["dep_kinds"]
            )
            package_id = dependency["pkg"]
            if is_normal and package_id not in visited:
                require(
                    package_id in nodes, f"cargo dependency has no node: {package_id}"
                )
                visited.add(package_id)
                pending.append(package_id)
    visited.remove(root)
    return visited


def build_ingestion_inventory(
    policy: Mapping[str, Any],
    *,
    metadata_by_platform: Mapping[str, Mapping[str, Any]] | None = None,
    lock_path: Path = INGESTION_LOCK_PATH,
) -> dict[str, Any]:
    """Build the Linux production Rust dependency inventory using Cargo itself."""
    if metadata_by_platform is None:
        metadata_by_platform = {
            platform: _cargo_metadata(target)
            for platform, target in INGESTION_TARGETS.items()
        }
    require(
        set(metadata_by_platform) == set(INGESTION_TARGETS),
        "cargo metadata must be supplied for both production Linux targets",
    )

    lock_packages = _cargo_lock_packages(lock_path)
    allowed = set(policy["ingestion"]["allowed_license_expressions"])
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    selected_platforms: dict[tuple[str, str, str], set[str]] = {}
    for platform, metadata in metadata_by_platform.items():
        packages_value = metadata.get("packages")
        require(
            isinstance(packages_value, list), "cargo metadata packages must be a list"
        )
        packages = {package["id"]: package for package in packages_value}
        for package_id in _normal_runtime_package_ids(metadata):
            require(
                package_id in packages,
                f"cargo runtime package is missing: {package_id}",
            )
            package = packages[package_id]
            source = package.get("source")
            if source is None:
                continue
            key = (package["name"], package["version"], source)
            require(
                key in lock_packages,
                f"cargo metadata package is absent from lock: {key}",
            )
            selected[key] = package
            selected_platforms.setdefault(key, set()).add(platform)

    dependencies: list[dict[str, Any]] = []
    for key in sorted(selected):
        package = selected[key]
        license_expression = package.get("license")
        require(
            isinstance(license_expression, str) and license_expression,
            f"Rust production dependency has no declared license: {key[0]}@{key[1]}",
        )
        require(
            license_expression in allowed,
            f"Rust dependency has an unreviewed license expression: "
            f"{key[0]}@{key[1]} ({license_expression})",
        )
        checksum = lock_packages[key].get("checksum")
        require(
            isinstance(checksum, str) and checksum,
            f"Rust registry dependency has no lock checksum: {key[0]}@{key[1]}",
        )
        dependencies.append(
            {
                "checksum": checksum,
                "license": license_expression,
                "name": key[0],
                "platforms": sorted(selected_platforms[key]),
                "source": key[2],
                "version": key[1],
            }
        )

    return {
        "artifact": "Studio ingestion statically linked production binary",
        "dependencies": dependencies,
        "format": INVENTORY_FORMAT,
        "scope": (
            "normal Cargo dependency closure for both published Linux targets; "
            "development-only and build-only dependencies are excluded"
        ),
        "source_lock": {
            "path": "ingestion/Cargo.lock",
            "sha256": sha256_file(lock_path),
        },
        "targets": INGESTION_TARGETS,
    }


def validate_cached_ingestion_inventory(
    policy: Mapping[str, Any],
    inventory: Mapping[str, Any],
    *,
    lock_path: Path = INGESTION_LOCK_PATH,
) -> None:
    """Perform fast lock-bound checks without downloading Cargo metadata."""
    require(
        inventory.get("format") == INVENTORY_FORMAT,
        "invalid ingestion inventory format",
    )
    require(
        inventory.get("source_lock")
        == {"path": "ingestion/Cargo.lock", "sha256": sha256_file(lock_path)},
        "ingestion inventory is not bound to the current Cargo.lock",
    )
    require(inventory.get("targets") == INGESTION_TARGETS, "invalid ingestion targets")
    dependencies = inventory.get("dependencies")
    require(
        isinstance(dependencies, list) and dependencies, "empty ingestion inventory"
    )
    lock_packages = _cargo_lock_packages(lock_path)
    allowed = set(policy["ingestion"]["allowed_license_expressions"])
    identities: list[tuple[str, str, str]] = []
    for dependency in dependencies:
        require(
            isinstance(dependency, dict), "ingestion dependency entry must be an object"
        )
        require(
            set(dependency)
            == {"checksum", "license", "name", "platforms", "source", "version"},
            "ingestion dependency entry has unexpected or missing fields",
        )
        key = (dependency["name"], dependency["version"], dependency["source"])
        require(
            key in lock_packages,
            f"ingestion inventory package is absent from lock: {key}",
        )
        require(
            dependency["checksum"] == lock_packages[key].get("checksum"),
            f"ingestion inventory checksum differs from lock: {key}",
        )
        require(
            dependency["license"] in allowed,
            f"ingestion inventory contains an unreviewed license: {key}",
        )
        platforms = dependency["platforms"]
        require(
            isinstance(platforms, list)
            and platforms
            and platforms == sorted(set(platforms))
            and set(platforms) <= set(INGESTION_TARGETS),
            f"invalid ingestion inventory platforms: {key}",
        )
        identities.append(key)
    require(
        identities == sorted(set(identities)),
        "ingestion dependency entries must be sorted and unique",
    )
    require(
        canonical_json(inventory)
        == INGESTION_INVENTORY_PATH.read_text(encoding="utf-8"),
        "ingestion inventory must use canonical JSON formatting",
    )


def validate_installed_frontend_override_evidence(policy: Mapping[str, Any]) -> None:
    """Verify manual npm license evidence against the exact installed package."""
    node_modules = STUDIO_ROOT / "frontend/node_modules"
    require(
        node_modules.is_dir(),
        "frontend node_modules is required for evidence validation",
    )
    for override in policy["frontend"]["manual_license_overrides"]:
        package_root = node_modules / override["name"]
        package_metadata = load_json(package_root / "package.json")
        require(
            package_metadata.get("version") == override["version"],
            f"installed override package version differs: {override['name']}",
        )
        evidence_path = package_root / override["license_file"]
        require(
            evidence_path.is_file(),
            f"manual license evidence is missing: {evidence_path}",
        )
        require(
            sha256_file(evidence_path) == override["evidence_sha256"],
            f"manual license evidence changed: {override['name']}@{override['version']}",
        )


def validate_frontend_build(dist: Path) -> None:
    """Prove the production static artifact excludes dependency source maps."""
    require(dist.is_dir(), f"frontend production build does not exist: {dist}")
    source_maps = sorted(
        path.relative_to(dist).as_posix() for path in dist.rglob("*.map")
    )
    require(
        not source_maps,
        f"frontend production build contains source maps: {source_maps}",
    )
    source_map_references: list[str] = []
    for pattern in ("*.js", "*.css"):
        for path in dist.rglob(pattern):
            if "sourceMappingURL=" in path.read_text(encoding="utf-8", errors="ignore"):
                source_map_references.append(path.relative_to(dist).as_posix())
    require(
        not source_map_references,
        f"frontend production build references source maps: {sorted(source_map_references)}",
    )


def validate_image_and_notice_contracts(policy: Mapping[str, Any]) -> None:
    """Require each production image to carry its owned license evidence."""
    license_root = "/usr/share/licenses/junjo-ai-studio/"
    common_copy = f"COPY LICENSE THIRD_PARTY_NOTICES.md {license_root}"
    expected_dockerfile_lines = {
        "backend/Dockerfile": {
            common_copy,
            f"COPY backend/uv.lock {license_root}backend-production.lock",
        },
        "frontend/Dockerfile": {
            common_copy,
            f"COPY licenses/frontend-production.json {license_root}",
        },
        "ingestion/Dockerfile": {
            common_copy,
            f"COPY licenses/ingestion-production.json {license_root}",
        },
    }
    for relative_path, lines in expected_dockerfile_lines.items():
        dockerfile = (STUDIO_ROOT / relative_path).read_text(encoding="utf-8")
        for line in lines:
            require(line in dockerfile, f"{relative_path} must contain: {line}")

    vite_config = (STUDIO_ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    require(
        "sourcemap: false" in vite_config and "sourcemap: true" not in vite_config,
        "Studio production frontend builds must explicitly disable source maps",
    )

    notice = (STUDIO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for required_text in (
        "licenses/frontend-production.json",
        "licenses/ingestion-production.json",
        "backend-production.lock",
        "license expressions are inventory",
        "not legal approval",
    ):
        require(
            required_text in notice,
            f"Studio third-party notice must explain {required_text}",
        )
    for binary in policy["external_binaries"]:
        for value in (
            binary["name"],
            binary["version"],
            binary["license"],
            binary["source"],
        ):
            require(
                value in notice,
                f"Studio third-party notice omits external binary: {value}",
            )
        ingestion_dockerfile = (STUDIO_ROOT / "ingestion/Dockerfile").read_text(
            encoding="utf-8"
        )
        require(
            f"GRPC_HEALTH_PROBE_VERSION=v{binary['version']}" in ingestion_dockerfile,
            f"ingestion Dockerfile version differs from license policy: {binary['name']}",
        )


def write_inventories(policy: Mapping[str, Any]) -> None:
    """Regenerate both committed inventories from their locked dependency graphs."""
    frontend = build_frontend_inventory(policy)
    ingestion = build_ingestion_inventory(policy)
    LICENSES_ROOT.mkdir(parents=True, exist_ok=True)
    FRONTEND_INVENTORY_PATH.write_text(canonical_json(frontend), encoding="utf-8")
    INGESTION_INVENTORY_PATH.write_text(canonical_json(ingestion), encoding="utf-8")


def check_inventories(
    policy: Mapping[str, Any],
    *,
    with_cargo_metadata: bool,
) -> None:
    """Check committed inventories against their current locks and policy."""
    expected_frontend = build_frontend_inventory(policy)
    require(
        FRONTEND_INVENTORY_PATH.is_file(), "frontend production inventory is missing"
    )
    require(
        FRONTEND_INVENTORY_PATH.read_text(encoding="utf-8")
        == canonical_json(expected_frontend),
        "frontend production inventory is stale; run the generator",
    )

    require(
        INGESTION_INVENTORY_PATH.is_file(), "ingestion production inventory is missing"
    )
    actual_ingestion = load_json(INGESTION_INVENTORY_PATH)
    require(isinstance(actual_ingestion, dict), "ingestion inventory must be an object")
    validate_cached_ingestion_inventory(policy, actual_ingestion)
    if with_cargo_metadata:
        expected_ingestion = build_ingestion_inventory(policy)
        require(
            INGESTION_INVENTORY_PATH.read_text(encoding="utf-8")
            == canonical_json(expected_ingestion),
            "ingestion production inventory is stale; run the generator",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("generate", help="rewrite both committed inventories")
    check = subparsers.add_parser("check", help="validate committed artifact evidence")
    check.add_argument(
        "--with-cargo-metadata",
        action="store_true",
        help="prove the exact Rust runtime closure by invoking cargo metadata",
    )
    check.add_argument(
        "--verify-installed-frontend",
        action="store_true",
        help="verify manual npm license evidence in the installed package tree",
    )
    check.add_argument(
        "--frontend-dist",
        type=Path,
        help="also reject source maps in this built production frontend directory",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy = load_policy()
    if args.command == "generate":
        write_inventories(policy)
        print("Studio production dependency license inventories regenerated.")
        return

    check_inventories(policy, with_cargo_metadata=args.with_cargo_metadata)
    validate_image_and_notice_contracts(policy)
    if args.verify_installed_frontend:
        validate_installed_frontend_override_evidence(policy)
    if args.frontend_dist is not None:
        dist = args.frontend_dist
        if not dist.is_absolute():
            dist = Path.cwd() / dist
        validate_frontend_build(dist.resolve())
    print("Studio artifact license evidence is current.")


if __name__ == "__main__":
    main()
