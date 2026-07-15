#!/usr/bin/env python3
"""Generate a static Cydia/Sileo APT repository from .deb files.

Usage:
    make_repo.py --debs DIR --out DIR [--repo-url URL]

Copies the debs to OUT/debs/ and writes Packages, Packages.gz, Packages.bz2,
Release and index.html to OUT/. Stdlib only — no dpkg/apt tooling required.
"""

import argparse
import bz2
import gzip
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

REPO_LABEL = "YTLite"
REPO_DESCRIPTION = "YTLite — lightweight YouTube client for iOS 12+"
ARCHITECTURES = "iphoneos-arm iphoneos-arm64"


def ar_members(data):
    """Yield (name, bytes) for each member of an ar archive."""
    if data[:8] != b"!<arch>\n":
        raise ValueError("not an ar archive")
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        body = data[offset + 60 : offset + 60 + size]
        yield name, body
        offset += 60 + size + (size % 2)  # members are 2-byte aligned


def read_control(deb_path):
    """Extract the control file text from a .deb."""
    data = deb_path.read_bytes()
    for name, body in ar_members(data):
        if name.startswith("control.tar"):
            with tarfile.open(fileobj=io.BytesIO(body), mode="r:*") as tar:
                for member in tar.getmembers():
                    if member.name.lstrip("./") == "control":
                        return tar.extractfile(member).read().decode("utf-8")
    raise ValueError(f"{deb_path.name}: no control file found")


def control_fields(control_text):
    fields = {}
    for line in control_text.splitlines():
        if line[:1].isspace() or ":" not in line:
            continue  # continuation lines of multi-line fields
        key, value = line.split(":", 1)
        fields[key] = value.strip()
    return fields


def version_key(version):
    return tuple(int(part) if part.isdigit() else 0 for part in version.split("."))


def package_stanza(deb_path, control_text):
    data = deb_path.read_bytes()
    stanza = control_text.strip()
    stanza += f"\nFilename: debs/{deb_path.name}"
    stanza += f"\nSize: {len(data)}"
    stanza += f"\nMD5sum: {hashlib.md5(data).hexdigest()}"
    stanza += f"\nSHA1: {hashlib.sha1(data).hexdigest()}"
    stanza += f"\nSHA256: {hashlib.sha256(data).hexdigest()}"
    return stanza + "\n"


def release_file(out_dir, index_names):
    lines = [
        f"Origin: {REPO_LABEL}",
        f"Label: {REPO_LABEL}",
        "Suite: stable",
        "Version: 1.0",
        "Codename: ios",
        f"Architectures: {ARCHITECTURES}",
        "Components: main",
        f"Description: {REPO_DESCRIPTION}",
    ]
    for field, algo in (("MD5Sum", "md5"), ("SHA256", "sha256")):
        lines.append(f"{field}:")
        for name in index_names:
            data = (out_dir / name).read_bytes()
            digest = hashlib.new(algo, data).hexdigest()
            lines.append(f" {digest} {len(data)} {name}")
    return "\n".join(lines) + "\n"


ARCH_LABELS = {"iphoneos-arm": "rootful", "iphoneos-arm64": "rootless"}


def version_list_html(entries):
    """entries: list of (version, arch, filename), newest first."""
    by_version = {}
    for version, arch, filename in entries:
        by_version.setdefault(version, []).append((arch, filename))
    items = []
    for version, debs in by_version.items():
        links = " · ".join(
            f'<a href="debs/{filename}">{ARCH_LABELS.get(arch, arch)}</a>'
            for arch, filename in sorted(debs)
        )
        items.append(f"<li><b>{version}</b> — {links}</li>")
    return "\n".join(items)


def index_html(repo_url, entries):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{REPO_LABEL} Repo</title>
<style>
 body {{ font-family: -apple-system, sans-serif; max-width: 600px;
        margin: 40px auto; padding: 0 16px; }}
 code {{ background: #eee; padding: 2px 6px; border-radius: 4px; }}
 a.btn {{ display: inline-block; margin: 4px 8px 4px 0; padding: 10px 16px;
         background: #d00; color: #fff; border-radius: 8px;
         text-decoration: none; }}
</style>
</head>
<body>
<h1>{REPO_LABEL} Repo</h1>
<p>{REPO_DESCRIPTION}.</p>
<p>Add <code>{repo_url}</code> to your package manager:</p>
<p>
<a class="btn" href="sileo://source/{repo_url}">Add to Sileo</a>
<a class="btn" href="zbra://sources/add/{repo_url}">Add to Zebra</a>
<a class="btn" href="cydia://url/https://cydia.saurik.com/api/share#?source={repo_url}">Add to Cydia</a>
</p>
<p>Rootful (<code>iphoneos-arm</code>) and rootless (<code>iphoneos-arm64</code>)
packages are provided. Any version below can be installed from the repo
(Sileo/Zebra: package page → version list) or downloaded directly:</p>
<ul>
{version_list_html(entries)}
</ul>
<p><a href="https://github.com/verback2308/YTLite">Project page on GitHub</a></p>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debs", required=True, type=Path, help="directory with .deb files")
    parser.add_argument("--out", required=True, type=Path, help="output directory for the repo")
    parser.add_argument("--repo-url", default="https://verback2308.github.io/YTLite/")
    args = parser.parse_args()

    debs = sorted(args.debs.glob("*.deb"))
    if not debs:
        raise SystemExit(f"no .deb files in {args.debs}")

    # Newest versions first, so both Packages and the index read top-down.
    parsed = [(deb, read_control(deb)) for deb in debs]
    parsed = [(deb, text, control_fields(text)) for deb, text in parsed]
    parsed.sort(key=lambda item: (version_key(item[2]["Version"]), item[2]["Architecture"]))
    parsed.reverse()

    debs_out = args.out / "debs"
    debs_out.mkdir(parents=True, exist_ok=True)
    for deb, _, _ in parsed:
        shutil.copy2(deb, debs_out / deb.name)

    packages = "\n".join(package_stanza(deb, text) for deb, text, _ in parsed)
    packages_bytes = packages.encode("utf-8")
    (args.out / "Packages").write_bytes(packages_bytes)
    # mtime=0 keeps the .gz byte-identical across runs for the same input
    (args.out / "Packages.gz").write_bytes(gzip.compress(packages_bytes, mtime=0))
    (args.out / "Packages.bz2").write_bytes(bz2.compress(packages_bytes))

    index_names = ["Packages", "Packages.gz", "Packages.bz2"]
    entries = [
        (fields["Version"], fields["Architecture"], deb.name) for deb, _, fields in parsed
    ]
    (args.out / "Release").write_text(release_file(args.out, index_names))
    (args.out / "index.html").write_text(index_html(args.repo_url, entries))

    print(f"Repo written to {args.out} ({len(debs)} package(s))")


if __name__ == "__main__":
    main()
