#!/usr/bin/env python3
"""KernelSU-Next DIY helper: keep manager package name, signing certificate,
Kotlin namespace, packaged library names, resources, and CI in sync.

The kernel accepts only a manager whose package name equals KSU_MANAGER_PACKAGE
and whose APK v2 signing certificate matches KSU_NEXT_MANAGER_SIZE and
KSU_NEXT_MANAGER_HASH (see kernel/manager/apk_sign.c). These values are
replicated across the kernel, ksud, the manager build, shortcuts, and CI, so
this tool updates and verifies all of them.

  python diy/ksu_diy.py info
  python diy/ksu_diy.py cert-info <cert.pem|cert.der|app.apk> ...
  python diy/ksu_diy.py check [--apk app.apk ...]
  python diy/ksu_diy.py verify-namespace [--namespace io.example.abcde]
  python diy/ksu_diy.py set-package com.example.manager
  python diy/ksu_diy.py set-cert path/to/cert.pem
  python diy/ksu_diy.py set-namespace io.example.abcde
"""

import argparse
import base64
import hashlib
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CERT_FILE = ROOT / "diy" / "manager-cert.pem"

KBUILD = ROOT / "kernel" / "Kbuild"
KERNEL_SETUP = ROOT / "kernel" / "setup.sh"
KSUD_BUILD_RS = ROOT / "userspace" / "ksud" / "build.rs"
KSUD_CLI_RS = ROOT / "userspace" / "ksud" / "src" / "cli.rs"
LATE_LOAD_RS = ROOT / "userspace" / "ksud" / "src" / "late_load.rs"

MANAGER_DIR = ROOT / "manager"
MANAGER_SETTINGS = MANAGER_DIR / "settings.gradle.kts"
MANAGER_GRADLE = MANAGER_DIR / "app" / "build.gradle.kts"
PROGUARD = MANAGER_DIR / "app" / "proguard-rules.pro"
MANAGER_JAVA = MANAGER_DIR / "app" / "src" / "main" / "java"
MANAGER_AIDL = MANAGER_DIR / "app" / "src" / "main" / "aidl"
MANAGER_CPP = MANAGER_DIR / "app" / "src" / "main" / "cpp"
MANAGER_RES = MANAGER_DIR / "app" / "src" / "main" / "res"
MANAGER_MANIFEST = MANAGER_DIR / "app" / "src" / "main" / "AndroidManifest.xml"
SHORTCUTS_XML = MANAGER_RES / "xml" / "shortcuts.xml"
JNI_CC = MANAGER_CPP / "jni.cc"
CMAKE = MANAGER_CPP / "CMakeLists.txt"
JNILIBS_GITIGNORE = MANAGER_DIR / "app" / "src" / "main" / "jniLibs" / ".gitignore"
UPDATE_BINARY_SH = MANAGER_DIR / "scripts" / "update_binary.sh"
MANAGER_SPOOF = MANAGER_DIR / "spoof"

BUILD_SH = ROOT / "build.sh"
JUSTFILE = ROOT / "justfile"
PRE_COMMIT = ROOT / ".githooks" / "pre-commit"
GITIGNORE = ROOT / ".gitignore"

WORKFLOWS_DIR = ROOT / ".github" / "workflows"
WF_BUILD_MANAGER = WORKFLOWS_DIR / "build-manager.yml"
WF_BUILD_MANAGER_CI = WORKFLOWS_DIR / "build-manager-ci.yml"
WF_DDK_LKM_KSU = WORKFLOWS_DIR / "ddk-lkm-ksu.yml"
KSUD_WORKFLOW = WORKFLOWS_DIR / "ksud.yml"
WF_RELEASE = WORKFLOWS_DIR / "release.yml"

# --- DIY identity & rename constants -----------------------------------------

OFFICIAL_NAMESPACE = "com.rifsxd.ksunext"
APP_NAME = "Toolbox"
PR_APP_NAME = "Toolbox PR"
APK_PREFIX = "Toolbox_"

JNI_LIB_NAME = "dsorft"
JNI_LIB = f"lib{JNI_LIB_NAME}.so"  # was libkernelsu.so
DAEMON_LIB = "libmbksab.so"        # was libksud.so

IDENTIFIER_RENAMES = [
    ("KernelSUApplication", "App"),
    ("WebUIActivity", "WebActivity"),
    ("MainActivity", "HomeActivity"),
    ("KsuService", "AppService"),
    ("IKsuInterface", "IAppInterface"),
    ("KernelSUTheme", "AppTheme"),
    ("Theme.KernelSU", "Theme.App"),
]

LITERAL_RENAMES = [
    ('"KernelSU-Next', '"Manager'),
    ('"KernelSU', '"Manager'),
    ('"KsuCli"', '"AppCli"'),
    ('"KsuService"', '"AppService"'),
    ("KsuService disconnected", "App service disconnected"),
    ("ksu_size.txt", "app_size.txt"),
    ("kernelsu-tmp-lkm.ko", "tmp-lkm.ko"),
    ("kernelsu://webui/", "app://webui/"),
]

RENAME_ROOTS = [
    MANAGER_DIR,
    LATE_LOAD_RS,
    BUILD_SH,
    JUSTFILE,
]

# Scan code, workflows, scripts and DIY docs; exclude pre-commit (which hosts
# the blocklist regex) and this script itself.
LEFTOVER_FILES_AND_DIRS = [
    MANAGER_DIR,
    ROOT / "userspace",
    ROOT / "kernel",
    ROOT / "scripts",
    ROOT / ".github",
    ROOT / ".github" / "copilot-instructions.md",
    BUILD_SH,
    JUSTFILE,
    ROOT / "DIY.md",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "GEMINI.md",
    ROOT / "diy" / "HANDOFF.md",
    ROOT / "diy" / "fetch_builds.py",
]

UPSTREAM_LEFTOVER_TOKENS = (
    "com.rifsxd.ksunext",
    "com/rifsxd/ksunext",
    "com_rifsxd_ksunext",
    "KernelSU_Next_",
    "libksud.so",
    "libkernelsu.so",
)

# Constructed piecewise to avoid self-matching leak checks inside this script.
OTHER_DIY_LEAK_TOKENS = (
    "com." + "cioputlxxcc",
    "com/" + "cioputlxxcc",
    "io." + "qzxnbqm",
    "io/" + "qzxnbqm",
    "io_" + "qzxnbqm",
    "fsh" + "qpk",
    "nse" + "qsv",
    "3a0f8ed2a39e8d3e8f61d7eb4499153a" + "97bd64f784a2072b4739a68cd643c3d8",
    "3a0f8ed2" + "3ab431cb",
)

LEGACY_CLASS_TOKENS = (
    "IKsuInterface",
    "KernelSUApplication",
    "MainActivity",
    "WebUIActivity",
    "KsuService",
    "KernelSUTheme",
)

TEXT_SUFFIXES = {
    ".kt", ".java", ".kts", ".xml", ".aidl", ".pro", ".json", ".toml",
    ".md", ".yml", ".yaml", ".gradle", ".sh", ".py", ".rs", ".c", ".h",
    ".cc", ".cpp", ".properties",
}
TEXT_NAMES = {"CMakeLists.txt", ".gitignore"}

NS_GRADLE_RE = re.compile(r'(namespace = ")([^"]+)(")')
NS_LATELOAD_RE = re.compile(r'(\{package_name\}/)([A-Za-z0-9_.]+)(\.ui\.HomeActivity)')
NS_JNI_RE = re.compile(r"Java_([A-Za-z0-9_]+)_Natives_")
NS_FINDCLASS_RE = re.compile(r'FindClass\("([A-Za-z0-9_/]+)/Natives\$Profile"\)')
SHORTCUT_PKG_RE = re.compile(r'(android:targetPackage=")([^"]+)(")')
SHORTCUT_CLS_RE = re.compile(r'(android:targetClass=")([A-Za-z0-9_.]+)(\.ui\.HomeActivity")')

# Must mirror kernel/manager/apk_sign.c and uapi/ksu.h
CERT_MAX_LENGTH = 1024
KSU_MAX_PACKAGE_NAME = 256
APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
V2_BLOCK_ID = 0x7109871A
VERITY_PADDING_ID = 0x42726577
KNOWN_BLOCK_IDS = {
    0xF05368C0: "v3 signature",
    0x1B93AD61: "v3.1 signature",
    0x6DFF800D: "source stamp",
    0x504B4453: "dependency info",
}

PR_SUFFIX = ".pr"
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")

# (file, regex, group -> meaning); each regex must match exactly once
LOCATIONS = [
    (
        KBUILD,
        re.compile(
            r"(ifeq \(\$\(KSU_IS_PR_BUILD\),1\)\r?\nKSU_MANAGER_PACKAGE (?:\?=|:=) )(\S+)(\r?\nelse\r?\nKSU_MANAGER_PACKAGE (?:\?=|:=) )(\S+)(\r?\nendif)"
        ),
        {2: "pr_package", 4: "package"},
    ),
    (KBUILD, re.compile(r"(\r?\nKSU_NEXT_MANAGER_SIZE (?:\?=|:=) )(\S+)()"), {2: "size"}),
    (KBUILD, re.compile(r"(\r?\nKSU_NEXT_MANAGER_HASH (?:\?=|:=) )(\S+)()"), {2: "hash"}),
    (KSUD_BUILD_RS, re.compile(r'(cargo:rustc-env=KSU_PACKAGE_NAME=)([^"]+)(")'), {2: "package"}),
    (
        MANAGER_GRADLE,
        re.compile(r'(val defaultManagerPackageName = if \(isPrBuild\) ")([^"]+)(" else ")([^"]+)(")'),
        {2: "pr_package", 4: "package"},
    ),
    (KSUD_WORKFLOW, re.compile(r'(export KSU_PACKAGE_NAME=")([^"$]+)(")'), {2: "pr_package"}),
    (WF_BUILD_MANAGER, re.compile(r'(echo "manager_package=)([^"]+)(" >> \$GITHUB_OUTPUT)'), {2: "pr_package"}),
    (WF_BUILD_MANAGER_CI, re.compile(r'(echo "manager_package=)([^"]+)(" >> \$GITHUB_OUTPUT)'), {2: "pr_package"}),
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES


def iter_scope_files(roots):
    seen = set()
    for root in roots:
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and is_text(path) and path not in seen:
                    seen.add(path)
                    yield path
        elif root.is_file():
            if root not in seen:
                seen.add(root)
                yield root


def read_one(path: Path, regex, group: int, what: str) -> str:
    matches = list(regex.finditer(read_text(path)))
    if len(matches) != 1:
        raise SystemExit(f"error: expected one {what} match in {rel(path)}, found {len(matches)}")
    return matches[0].group(group)


def read_unique(path: Path, regex, group: int, what: str) -> str:
    values = {m.group(group) for m in regex.finditer(read_text(path))}
    if len(values) != 1:
        raise SystemExit(f"error: expected one unique {what} value in {rel(path)}, found {len(values)}")
    return next(iter(values))


def read_unique_safe(path: Path, regex, group: int, what: str, errors: list) -> str | None:
    if not path.is_file():
        errors.append(f"missing {rel(path)}")
        return None
    values = {m.group(group) for m in regex.finditer(read_text(path))}
    if len(values) != 1:
        errors.append(f"expected one unique {what} value in {rel(path)}, found {len(values)}")
        return None
    return next(iter(values))


def read_one_safe(path: Path, regex, group: int, what: str, errors: list) -> str | None:
    if not path.is_file():
        errors.append(f"missing {rel(path)}")
        return None
    matches = list(regex.finditer(read_text(path)))
    if len(matches) != 1:
        errors.append(f"expected one {what} match in {rel(path)}, found {len(matches)}")
        return None
    return matches[0].group(group)


def apply_renames(text: str, ns: str, path: Path) -> str:
    ns_slash = ns.replace(".", "/")
    ns_under = ns.replace(".", "_")
    text = text.replace(OFFICIAL_NAMESPACE, ns)
    text = text.replace(OFFICIAL_NAMESPACE.replace(".", "/"), ns_slash)
    text = text.replace(OFFICIAL_NAMESPACE.replace(".", "_") + "_", ns_under + "_")
    for old, new in IDENTIFIER_RENAMES:
        text = text.replace(old, new)
    in_sources = path.is_relative_to(MANAGER_JAVA) or path.is_relative_to(MANAGER_CPP)
    if in_sources:
        for old, new in LITERAL_RENAMES:
            text = text.replace(old, new)
    text = text.replace('System.loadLibrary("kernelsu")', f'System.loadLibrary("{JNI_LIB_NAME}")')
    text = text.replace("libksud.so", DAEMON_LIB)
    if path == CMAKE:
        text = re.sub(r"\bkernelsu\b", JNI_LIB_NAME, text)
    return text


class ApkError(Exception):
    pass


def load_cert(path: Path) -> bytes:
    data = path.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in data:
        pem = data.split(b"-----BEGIN CERTIFICATE-----", 1)[1].split(b"-----END CERTIFICATE-----", 1)[0]
        return base64.b64decode(b"".join(pem.split()))
    return data


def describe_cert(der: bytes) -> tuple[int, str]:
    return len(der), hashlib.sha256(der).hexdigest()


def read_apk_cert(path: Path) -> tuple[bytes, list[str]]:
    """Return (certificate DER, list of reasons kernel/manager/apk_sign.c would reject the APK)."""
    data = path.read_bytes()
    size = len(data)

    def u16(off):
        return struct.unpack_from("<H", data, off)[0]

    def u32(off):
        return struct.unpack_from("<I", data, off)[0]

    def u64(off):
        return struct.unpack_from("<Q", data, off)[0]

    eocd = None
    for i in range(0x10000):
        pos = size - i - 2
        if pos - 20 < 0:
            break
        if u16(pos) == i and u32(pos - 20) == 0x06054B50:
            eocd = pos - 20
            break
    if eocd is None:
        raise ApkError("cannot find ZIP end of central directory")
    if eocd >= 20 and u32(eocd - 20) == 0x07064B50:
        raise ApkError("ZIP64 APKs are rejected by the kernel")

    cd_size, cd_offset = u32(eocd + 12), u32(eocd + 16)
    if cd_offset > eocd or cd_size != eocd - cd_offset or cd_offset < 0x20:
        raise ApkError("malformed central directory")

    pairs_end = cd_offset - 0x18
    block_size = u64(pairs_end)
    if data[pairs_end + 8 : pairs_end + 24] != APK_SIG_BLOCK_MAGIC:
        raise ApkError("no APK Signing Block (v1-only or unsigned APK)")
    if block_size < 0x18 or block_size > cd_offset - 8:
        raise ApkError("malformed APK Signing Block size")
    pos = cd_offset - block_size - 8
    if u64(pos) != block_size:
        raise ApkError("APK Signing Block size mismatch")
    pos += 8

    problems = []
    certs = []
    while pos < pairs_end:
        pair_size = u64(pos)
        pos += 8
        if pair_size < 4 or pair_size > pairs_end - pos:
            raise ApkError("malformed signing block pair")
        pair_end = pos + pair_size
        block_id = u32(pos)
        if block_id == V2_BLOCK_ID:
            certs.append(parse_v2_block(data, pos + 4, pair_end))
        elif block_id != VERITY_PADDING_ID:
            name = KNOWN_BLOCK_IDS.get(block_id, "unknown block")
            problems.append(f"contains {name} (0x{block_id:08x}); sign with v2 only")
        pos = pair_end

    if len(certs) != 1:
        raise ApkError(f"expected exactly one v2 signature block, found {len(certs)}")
    cert = certs[0]
    if len(cert) > CERT_MAX_LENGTH:
        problems.append(f"certificate is {len(cert)} bytes, kernel limit is {CERT_MAX_LENGTH}")
    return cert, problems


def parse_v2_block(data: bytes, pos: int, end: int) -> bytes:
    def length_prefixed(pos, end):
        if pos + 4 > end:
            raise ApkError("truncated v2 block")
        length = struct.unpack_from("<I", data, pos)[0]
        if length > end - pos - 4:
            raise ApkError("truncated v2 block")
        return pos + 4, pos + 4 + length

    pos, signers_end = length_prefixed(pos, end)
    pos, signer_end = length_prefixed(pos, signers_end)
    pos, signed_data_end = length_prefixed(pos, signer_end)
    _, digests_end = length_prefixed(pos, signed_data_end)
    pos, certs_end = length_prefixed(digests_end, signed_data_end)
    pos, cert_end = length_prefixed(pos, certs_end)
    return data[pos:cert_end]


def read_locations(errors: list[str] | None = None) -> dict:
    """Collect configured values as {meaning: {value: [files]}}."""
    found = {}
    for path, regex, groups in LOCATIONS:
        if not path.is_file():
            msg = f"missing {rel(path)}"
            if errors is not None:
                errors.append(msg)
                continue
            raise SystemExit(f"error: {msg}")
        matches = list(regex.finditer(read_text(path)))
        if len(matches) != 1:
            msg = f"expected one match of {regex.pattern!r} in {rel(path)}, found {len(matches)}"
            if errors is not None:
                errors.append(msg)
                continue
            raise SystemExit(f"error: {msg}")
        for group, meaning in groups.items():
            found.setdefault(meaning, {}).setdefault(matches[0].group(group), []).append(rel(path))
    return found


def rewrite(updates: dict[str, str]) -> None:
    """Replace configured values across LOCATIONS."""
    for path in dict.fromkeys(loc[0] for loc in LOCATIONS):
        text = original = read_text(path)
        for _, regex, groups in (loc for loc in LOCATIONS if loc[0] == path):
            wanted = {g: updates[m] for g, m in groups.items() if m in updates}
            if not wanted:
                continue

            def repl(match, regex=regex, wanted=wanted):
                return "".join(wanted.get(g, match.group(g)) for g in range(1, regex.groups + 1))

            text, count = regex.subn(repl, text)
            if count != 1:
                raise SystemExit(f"error: expected one match in {rel(path)}, found {count}")
        if text != original:
            write_text(path, text)
            print(f"updated {rel(path)}")


def require_tokens(path: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing {rel(path)}")
        return
    text = read_text(path)
    for token in tokens:
        if token not in text:
            errors.append(f"{rel(path)} is missing {token!r}")


def forbid_tokens(path: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    if not path.is_file():
        return
    text = read_text(path)
    for token in tokens:
        if token in text:
            errors.append(f"{rel(path)} still contains forbidden {token!r}")


def verify_namespace(ns: str, package: str | None = None) -> list[str]:
    """Cross-check namespace, component renames, native libs, and resources."""
    errors: list[str] = []
    ns_slash = ns.replace(".", "/")
    ns_under = ns.replace(".", "_")

    def check_equal(label: str, value: str | None):
        if value is not None and value != ns:
            errors.append(f"{label} uses {value!r}, expected namespace {ns!r}")

    check_equal("manager/app/build.gradle.kts", read_one_safe(MANAGER_GRADLE, NS_GRADLE_RE, 2, "namespace", errors))

    jni_prefix = read_unique_safe(JNI_CC, NS_JNI_RE, 1, "JNI symbol namespace", errors)
    if jni_prefix is not None and jni_prefix != ns_under:
        errors.append(f"manager/app/src/main/cpp/jni.cc Java_ prefix uses {jni_prefix!r}, expected {ns_under!r}")

    findclass = read_unique_safe(JNI_CC, NS_FINDCLASS_RE, 1, "FindClass namespace", errors)
    if findclass is not None and findclass != ns_slash:
        errors.append(f"manager/app/src/main/cpp/jni.cc FindClass uses {findclass!r}, expected {ns_slash!r}")

    if JNI_CC.is_file() and '#define LOG_TAG "Manager"' not in read_text(JNI_CC):
        errors.append('manager/app/src/main/cpp/jni.cc must define #define LOG_TAG "Manager"')

    check_equal("userspace/ksud/src/late_load.rs am-start component", read_one_safe(LATE_LOAD_RS, NS_LATELOAD_RE, 2, "late-load component", errors))

    if MANAGER_MANIFEST.is_file():
        manifest = read_text(MANAGER_MANIFEST)
        for comp in (
            'android:name=".App"',
            'android:name=".ui.HomeActivity"',
            'android:targetActivity=".ui.HomeActivity"',
            'android:name=".ui.webui.WebActivity"',
            'android:theme="@style/Theme.App"',
            'android:theme="@style/Theme.App.WebUI"',
        ):
            if comp not in manifest:
                errors.append(f"AndroidManifest.xml is missing {comp}")
        for old in ("KernelSUApplication", "MainActivity", "WebUIActivity", "Theme.KernelSU", "KsuService"):
            if old in manifest:
                errors.append(f"AndroidManifest.xml still references {old!r}")
    else:
        errors.append(f"missing {rel(MANAGER_MANIFEST)}")

    aidl = MANAGER_AIDL.joinpath(*ns.split("."), "IAppInterface.aidl")
    if not aidl.is_file():
        errors.append(f"missing {rel(aidl)}")
    else:
        aidl_text = read_text(aidl)
        if not re.search(rf"^package {re.escape(ns)};\r?$", aidl_text, re.MULTILINE):
            errors.append(f"{rel(aidl)} does not declare package {ns}")
        if "interface IAppInterface" not in aidl_text:
            errors.append(f"{rel(aidl)} does not declare interface IAppInterface")

    for base in (MANAGER_JAVA, MANAGER_AIDL):
        old_dir = base.joinpath(*OFFICIAL_NAMESPACE.split("."))
        new_dir = base.joinpath(*ns.split("."))
        if old_dir.exists():
            errors.append(f"official source dir still exists: {rel(old_dir)}")
        if not new_dir.is_dir():
            errors.append(f"renamed source dir missing: {rel(new_dir)}")

    if PROGUARD.is_file():
        proguard = read_text(PROGUARD)
        for line in (
            f"-keep class {ns}.Natives {{ *; }}",
            f"-keep class {ns}.Natives$Profile {{ *; }}",
        ):
            if line not in proguard:
                errors.append(f"proguard-rules.pro is missing: {line}")
    else:
        errors.append(f"missing {rel(PROGUARD)}")

    if CMAKE.is_file():
        cmake = read_text(CMAKE)
        for req in (f'project("{JNI_LIB_NAME}")', f"add_library({JNI_LIB_NAME}", "adbroot"):
            if req not in cmake:
                errors.append(f"CMakeLists.txt is missing {req!r}")
        if "kernelsu" in cmake:
            errors.append("CMakeLists.txt still references old JNI library name")
    else:
        errors.append(f"missing {rel(CMAKE)}")

    ns_java = MANAGER_JAVA.joinpath(*ns.split("."))
    require_tokens(ns_java / "Natives.kt", (f'System.loadLibrary("{JNI_LIB_NAME}")',), errors)
    require_tokens(ns_java / "ui" / "util" / "KsuCli.kt", ('"AppCli"', DAEMON_LIB, 'Log.i("Manager",', '"tmp-lkm.ko"'), errors)
    require_tokens(ns_java / "ui" / "util" / "Downloader.kt", ("BuildConfig.UPDATE_REPO.isBlank()", "BuildConfig.UPDATE_REPO"), errors)
    require_tokens(ns_java / "App.kt", ("class App", "Manager/"), errors)
    require_tokens(ns_java / "ui" / "HomeActivity.kt", ("class HomeActivity", "AppTheme"), errors)
    require_tokens(ns_java / "ui" / "webui" / "WebActivity.kt", ("class WebActivity",), errors)
    require_tokens(ns_java / "ui" / "theme" / "Theme.kt", ("fun AppTheme",), errors)
    require_tokens(ns_java / "ui" / "component" / "AboutCard.kt", ("R.drawable.ic_launcher_foreground",), errors)

    app_service = ns_java / "ui" / "AppService.kt"
    if not app_service.is_file():
        app_service = ns_java / "AppService.kt"
    require_tokens(app_service, ("class AppService", "IAppInterface", '"AppService"'), errors)

    for rel_sub in ("ui/screen/Home.kt", "ui/screen/Module.kt", "ui/util/module/Shortcut.kt"):
        p = ns_java.joinpath(*rel_sub.split("/"))
        require_tokens(p, ("app://webui/",), errors)
        forbid_tokens(p, ("kernelsu://webui/",), errors)

    shortcut_cls_ns = read_unique_safe(SHORTCUTS_XML, SHORTCUT_CLS_RE, 2, "shortcut targetClass namespace", errors)
    if shortcut_cls_ns is not None and shortcut_cls_ns != ns:
        errors.append(f"shortcuts.xml targetClass namespace is {shortcut_cls_ns!r}, expected {ns!r}")
    if package is not None:
        shortcut_pkg = read_unique_safe(SHORTCUTS_XML, SHORTCUT_PKG_RE, 2, "shortcut targetPackage", errors)
        if shortcut_pkg is not None and shortcut_pkg != package:
            errors.append(f"shortcuts.xml targetPackage is {shortcut_pkg!r}, expected {package!r}")

    return errors


def check_repo_rules(package: str, pr_package: str) -> list[str]:
    """Check 16-kernelSU-Next specific DIY settings, resources, hooks, and CI workflows."""
    errors: list[str] = []

    require_tokens(KBUILD, ("KSU_IS_PR_BUILD ?= 0", "ifndef KSU_MANAGER_PACKAGE", "ifdef KSU_MANAGER_PACKAGE"), errors)
    require_tokens(KERNEL_SETUP, ('KSU_REPO_URL="${KSU_REPO_URL:-https://github.com/$OWNER/$REPO}"', 'git clone "$KSU_REPO_URL"'), errors)
    require_tokens(KSUD_BUILD_RS, ('println!("cargo:rerun-if-env-changed=KSU_PACKAGE_NAME");',), errors)

    if KSUD_CLI_RS.is_file():
        cli_txt = read_text(KSUD_CLI_RS)
        count = cli_txt.count('env!("KSU_PACKAGE_NAME")')
        if count != 3:
            errors.append(f"userspace/ksud/src/cli.rs should use env!(\"KSU_PACKAGE_NAME\") 3 times, found {count}")
    else:
        errors.append(f"missing {rel(KSUD_CLI_RS)}")

    require_tokens(MANAGER_SETTINGS, (f'rootProject.name = "{APP_NAME}"',), errors)
    require_tokens(
        MANAGER_GRADLE,
        (
            f'val defaultManagerName = if (isPrBuild) "{PR_APP_NAME}" else "{APP_NAME}"',
            'val managerUpdateRepo = findProperty("KSU_UPDATE_REPO")?.toString() ?: System.getenv("KSU_UPDATE_REPO") ?: ""',
            'buildConfigField("boolean", "IS_PR_BUILD"',
            'buildConfigField("String", "UPDATE_REPO"',
            'resValue("string", "app_name", managerName)',
            f'output.outputFileName = "{APK_PREFIX}',
        ),
        errors,
    )

    for theme_path in (MANAGER_RES / "values" / "themes.xml", MANAGER_RES / "values-night" / "themes.xml"):
        require_tokens(theme_path, ('name="Theme.App"', 'name="Theme.App.WebUI"'), errors)
        forbid_tokens(theme_path, ("Theme.KernelSU",), errors)

    require_tokens(MANAGER_RES / "values" / "colors.xml", ('<color name="ic_launcher_foreground">#FF1E110D</color>',), errors)
    require_tokens(MANAGER_RES / "drawable" / "ic_launcher_foreground.xml", ("<vector",), errors)
    require_tokens(MANAGER_RES / "drawable" / "ic_launcher_monochrome.xml", ("<vector",), errors)
    require_tokens(
        MANAGER_RES / "mipmap-anydpi" / "ic_launcher.xml",
        ("@drawable/ic_launcher_foreground", "@drawable/ic_launcher_monochrome"),
        errors,
    )
    forbid_tokens(MANAGER_RES / "mipmap-anydpi" / "ic_launcher.xml", ("@mipmap/ic_launcher_foreground", "@mipmap/ic_launcher_monochrome"), errors)

    strings_files = sorted(MANAGER_RES.glob("values*/strings.xml"))
    if not strings_files:
        errors.append("no res/values*/strings.xml files found")
    for sf in strings_files:
        try:
            xml_root = ET.fromstring(read_text(sf))
        except ET.ParseError as e:
            errors.append(f"{rel(sf)} failed XML parsing: {e}")
            continue
        for elem in xml_root.iter():
            if elem.attrib.get("name") == "app_name":
                errors.append(f'{rel(sf)} must not define app_name (injected via build.gradle.kts resValue)')

    leftover_launcher_pngs = sorted(MANAGER_RES.glob("mipmap-*/ic_launcher*.png"))
    for png in leftover_launcher_pngs:
        errors.append(f"forbidden launcher PNG still exists: {rel(png)}")

    if MANAGER_SPOOF.exists():
        errors.append(f"forbidden upstream spoof script still exists: {rel(MANAGER_SPOOF)}")

    require_tokens(JNILIBS_GITIGNORE, (DAEMON_LIB,), errors)
    forbid_tokens(JNILIBS_GITIGNORE, ("libksud.so",), errors)
    require_tokens(UPDATE_BINARY_SH, (DAEMON_LIB,), errors)
    forbid_tokens(UPDATE_BINARY_SH, ("libksud.so",), errors)

    require_tokens(BUILD_SH, (DAEMON_LIB, APK_PREFIX), errors)
    forbid_tokens(BUILD_SH, ("libksud.so", "KernelSU_Next_"), errors)
    require_tokens(JUSTFILE, (DAEMON_LIB,), errors)
    forbid_tokens(JUSTFILE, ("libksud.so",), errors)

    require_tokens(GITIGNORE, (".diy-secrets/", "*.jks", "*.p12", "*.keystore", "builds/"), errors)
    require_tokens(PRE_COMMIT, (".diy-secrets/", "com\\.rifsxd\\.ksunext", "libksud\\.so", "diy/ksu_diy.py check"), errors)

    for wf in (WF_BUILD_MANAGER, WF_BUILD_MANAGER_CI):
        require_tokens(
            wf,
            (
                "generate-key",
                "apksigner",
                "--v1-signing-enabled false",
                "--v2-signing-enabled true",
                "--v3-signing-enabled false",
                "--v4-signing-enabled false",
                "verify --verbose",
                "ksu_diy.py check",
                "--apk",
                DAEMON_LIB,
            ),
            errors,
        )
        forbid_tokens(wf, ("spoofed", "./spoof", "manager-spoofed", "libksud.so"), errors)

    require_tokens(WF_BUILD_MANAGER_CI, ('"main"', '"dev"', "'diy/**'"), errors)
    require_tokens(
        WF_DDK_LKM_KSU,
        ("safe.directory '*'", "KSU_MANAGER_PACKAGE", "KSU_NEXT_MANAGER_SIZE", "KSU_NEXT_MANAGER_HASH", "KSU_IS_PR_BUILD"),
        errors,
    )
    forbid_tokens(WF_DDK_LKM_KSU, ("/__w/KernelSU-Next/KernelSU-Next",), errors)
    require_tokens(KSUD_WORKFLOW, ("KSU_PACKAGE_NAME",), errors)

    if WF_RELEASE.is_file():
        active_lines = [ln for ln in read_text(WF_RELEASE).splitlines() if not ln.lstrip().startswith("#")]
        active_text = "\n".join(active_lines)
        if re.search(r"^\s*push\s*:", active_text, re.MULTILINE) or re.search(r"^\s*tags\s*:", active_text, re.MULTILINE):
            errors.append("release.yml must not enable automatic tag-push releases")
        if "workflow_dispatch:" not in active_text:
            errors.append("release.yml should keep workflow_dispatch trigger")
    else:
        errors.append(f"missing {rel(WF_RELEASE)}")

    for path in iter_scope_files(LEFTOVER_FILES_AND_DIRS):
        text = read_text(path)
        for token in UPSTREAM_LEFTOVER_TOKENS + OTHER_DIY_LEAK_TOKENS:
            if token in text:
                errors.append(f"{rel(path)} still contains forbidden literal {token!r}")

    for path in iter_scope_files([MANAGER_DIR / "app" / "src", ROOT / "userspace" / "ksud" / "src"]):
        text = read_text(path)
        for token in LEGACY_CLASS_TOKENS:
            if token in text:
                errors.append(f"{rel(path)} still contains legacy symbol {token!r}")

    return errors


def check_apk_contents(path: Path, package: str, errors: list[str], notes: list[str]) -> None:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for arch in ("arm64-v8a", "x86_64", "riscv64"):
            for lib in (JNI_LIB, DAEMON_LIB):
                if f"lib/{arch}/{lib}" not in names:
                    errors.append(f"{path}: missing lib/{arch}/{lib}")
        for name in sorted(names):
            if name.endswith("libkernelsu.so") or name.endswith("libksud.so"):
                errors.append(f"{path}: still contains {name}")

        if "AndroidManifest.xml" not in names:
            errors.append(f"{path}: missing AndroidManifest.xml")
        else:
            manifest = z.read("AndroidManifest.xml")
            for expected in (".App", ".ui.HomeActivity", ".ui.webui.WebActivity"):
                if expected.encode("utf-8") not in manifest and expected.encode("utf-16-le") not in manifest:
                    errors.append(f"{path}: binary manifest missing {expected!r}")
            for forbidden in ("com.rifsxd.ksunext", "KernelSUApplication", "MainActivity", "WebUIActivity", "Theme.KernelSU", "KsuService"):
                if forbidden.encode("utf-8") in manifest or forbidden.encode("utf-16-le") in manifest:
                    errors.append(f"{path}: binary manifest still contains {forbidden!r}")

        for member in sorted(names):
            if not re.fullmatch(r"classes\d*\.dex", member):
                continue
            data = z.read(member)
            for token in (
                b"com/rifsxd",
                b"com.rifsxd",
                b"com_rifsxd_ksunext",
                b"KernelSU_Next_",
                *(t.encode("utf-8") for t in OTHER_DIY_LEAK_TOKENS[:7]),
            ):
                count = data.count(token)
                if count:
                    errors.append(f"{path}: {member} still contains {token.decode()} ({count}x)")
            for token in (b"kernelsu", b"KernelSU", b"ksud", b"Ksu"):
                count = data.count(token)
                if count:
                    notes.append(f"note: {member} contains {token.decode()} ({count}x)")


def cmd_info(_args) -> int:
    errors: list[str] = []
    found = read_locations(errors)
    ns = read_one_safe(MANAGER_GRADLE, NS_GRADLE_RE, 2, "namespace", errors)

    def summarize(key: str) -> str:
        vals = found.get(key, {})
        if not vals:
            return "<missing>"
        if len(vals) == 1:
            return next(iter(vals))
        return "INCONSISTENT: " + "; ".join(f"{v!r} ({', '.join(fs)})" for v, fs in vals.items())

    cert_status = "<missing>"
    if CERT_FILE.is_file():
        c_size, c_hash = describe_cert(load_cert(CERT_FILE))
        cert_status = f"0x{c_size:04x} ({c_size} bytes) sha256={c_hash}"

    print(f"app name     : {APP_NAME} (PR: {PR_APP_NAME}, prefix: {APK_PREFIX})")
    print(f"package name : {summarize('package')} (PR: {summarize('pr_package')})")
    print(f"namespace    : {ns or '<missing>'}")
    print(f"libraries    : {JNI_LIB} (JNI target={JNI_LIB_NAME}), {DAEMON_LIB} (daemon)")
    print(f"kernel cert  : size={summarize('size')} hash={summarize('hash')}")
    print(f"cert pem     : {rel(CERT_FILE)} -> {cert_status}")
    for err in errors:
        print(f"warning      : {err}", file=sys.stderr)
    return 0 if not errors else 1


def cmd_cert_info(args) -> int:
    status = 0
    for name in args.files:
        path = Path(name)
        problems = []
        if path.read_bytes()[:2] == b"PK":
            try:
                der, problems = read_apk_cert(path)
            except ApkError as e:
                print(f"{name}: REJECTED by kernel: {e}")
                status = 1
                continue
        else:
            der = load_cert(path)
        size, digest = describe_cert(der)
        print(f"{name}:\n  KSU_NEXT_MANAGER_SIZE=0x{size:04x} ({size} bytes)\n  KSU_NEXT_MANAGER_HASH={digest}")
        for problem in problems:
            print(f"  REJECTED by kernel: {problem}")
            status = 1
    return status


def cmd_verify_namespace(args) -> int:
    ns = args.namespace or read_one(MANAGER_GRADLE, NS_GRADLE_RE, 2, "namespace")
    errors = verify_namespace(ns)
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"namespace verified: {ns}")
    return 0


def cmd_check(args) -> int:
    errors: list[str] = []
    found = read_locations(errors)
    for meaning, values in found.items():
        if len(values) != 1:
            detail = "; ".join(f"{v!r} in {', '.join(files)}" for v, files in values.items())
            errors.append(f"inconsistent {meaning}: {detail}")

    package = next(iter(found.get("package", {})), None)
    pr_package = next(iter(found.get("pr_package", {})), None)
    if package and pr_package and pr_package != package + PR_SUFFIX:
        errors.append(f"PR package {pr_package!r} should be {package + PR_SUFFIX!r}")
    if package and package.startswith(OFFICIAL_NAMESPACE):
        errors.append("package name is still the official one")

    size_str = next(iter(found.get("size", {})), None)
    digest = next(iter(found.get("hash", {})), None)
    size = int(size_str, 0) if size_str else None
    if digest and (digest != digest.lower() or len(digest) != 64):
        errors.append("KSU_NEXT_MANAGER_HASH must be 64 lowercase hex characters")

    if not CERT_FILE.is_file():
        errors.append(f"missing certificate file: {rel(CERT_FILE)}")
    elif size is not None and digest is not None:
        cert_size, cert_digest = describe_cert(load_cert(CERT_FILE))
        if (cert_size, cert_digest) != (size, digest):
            errors.append(
                f"kernel/Kbuild expects size 0x{size:04x} hash {digest}, "
                f"but {rel(CERT_FILE)} is 0x{cert_size:04x} {cert_digest}"
            )

    ns = read_one_safe(MANAGER_GRADLE, NS_GRADLE_RE, 2, "namespace", errors)
    if ns:
        errors.extend(verify_namespace(ns, package=package))
    if package and pr_package:
        errors.extend(check_repo_rules(package, pr_package))

    notes: list[str] = []
    for apk in args.apk or []:
        apk_path = Path(apk)
        try:
            der, problems = read_apk_cert(apk_path)
        except ApkError as e:
            errors.append(f"{apk}: {e}")
            continue
        errors.extend(f"{apk}: {p}" for p in problems)
        apk_size, apk_digest = describe_cert(der)
        if size is not None and digest is not None and (apk_size, apk_digest) != (size, digest):
            errors.append(
                f"{apk}: signed with 0x{apk_size:04x} {apk_digest}, "
                f"kernel expects 0x{size:04x} {digest} (wrong keystore?)"
            )
        if package:
            check_apk_contents(apk_path, package, errors, notes)

    print(f"package name : {package or '<error>'} (PR: {pr_package or '<error>'})")
    print(f"certificate  : size={f'0x{size:04x}' if size is not None else '<error>'} hash={digest or '<error>'}")
    print(f"namespace    : {ns or '<error>'}")
    print(f"libraries    : {JNI_LIB} (JNI), {DAEMON_LIB} (daemon)")
    for apk in args.apk or []:
        print(f"checked apk  : {apk}")
    for note in notes:
        print(note)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("OK")
    return 0


def cmd_set_package(args) -> int:
    name = args.package
    if not PACKAGE_RE.match(name):
        raise SystemExit(f"error: {name!r} is not a valid Android package name")
    if len(name + PR_SUFFIX) >= KSU_MAX_PACKAGE_NAME - 1:
        raise SystemExit("error: package name too long")

    old_found = read_locations()
    old_pkg = next(iter(old_found["package"]))
    old_pr_pkg = next(iter(old_found["pr_package"]))
    new_pr_pkg = name + PR_SUFFIX

    rewrite({"package": name, "pr_package": new_pr_pkg})

    if SHORTCUTS_XML.is_file():
        txt = orig = read_text(SHORTCUTS_XML)
        txt = SHORTCUT_PKG_RE.sub(rf'\g<1>{name}\g<3>', txt)
        if txt != orig:
            write_text(SHORTCUTS_XML, txt)
            print(f"updated {rel(SHORTCUTS_XML)}")

    for wf in (WF_BUILD_MANAGER, WF_BUILD_MANAGER_CI):
        if wf.is_file():
            txt = orig = read_text(wf)
            txt = txt.replace(old_pr_pkg, new_pr_pkg).replace(old_pkg, name)
            if txt != orig:
                write_text(wf, txt)
                print(f"updated {rel(wf)}")
    return 0


def cmd_set_cert(args) -> int:
    src = Path(args.cert)
    if src.read_bytes()[:2] == b"PK":
        try:
            der, problems = read_apk_cert(src)
        except ApkError as e:
            raise SystemExit(f"error: {src}: {e}")
        if problems:
            raise SystemExit(f"error: {src}: " + "; ".join(problems))
    else:
        der = load_cert(src)
    size, digest = describe_cert(der)
    if size > CERT_MAX_LENGTH:
        raise SystemExit(f"error: certificate is {size} bytes, kernel limit is {CERT_MAX_LENGTH} (use RSA 2048 or EC)")
    if src.resolve() != CERT_FILE.resolve():
        if b"-----BEGIN CERTIFICATE-----" in src.read_bytes():
            shutil.copyfile(src, CERT_FILE)
        else:
            b64 = base64.encodebytes(der).decode().replace("\n", "")
            lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
            pem = "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"
            CERT_FILE.write_bytes(pem.encode())
        print(f"updated {rel(CERT_FILE)}")
    rewrite({"size": f"0x{size:04x}", "hash": digest})
    return 0


def cmd_set_namespace(args) -> int:
    ns = args.namespace
    if not PACKAGE_RE.match(ns):
        raise SystemExit(f"error: {ns!r} is not a valid namespace")
    if ns.startswith(OFFICIAL_NAMESPACE):
        raise SystemExit("error: the new namespace must not keep the official prefix")

    moved = 0
    for base in (MANAGER_JAVA, MANAGER_AIDL):
        old = base.joinpath(*OFFICIAL_NAMESPACE.split("."))
        new = base.joinpath(*ns.split("."))
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
            moved += 1
        elif not new.exists():
            raise SystemExit(f"error: neither {rel(old)} nor {rel(new)} exists")

    # Upstream placed KsuService.kt at root with `package ...ui;` -> align to ui/AppService.kt
    ns_java = MANAGER_JAVA.joinpath(*ns.split("."))
    root_ksu_service = ns_java / "KsuService.kt"
    ui_app_service = ns_java / "ui" / "AppService.kt"
    if root_ksu_service.is_file() and not ui_app_service.exists():
        ui_app_service.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root_ksu_service), str(ui_app_service))
        moved += 1

    for base in (MANAGER_JAVA, MANAGER_AIDL):
        for path in sorted(base.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            new_name = path.name
            for old, new in IDENTIFIER_RENAMES:
                new_name = new_name.replace(old, new)
            if new_name != path.name:
                shutil.move(str(path), str(path.with_name(new_name)))
                moved += 1

    for path in iter_scope_files(RENAME_ROOTS):
        text = read_text(path)
        updated = apply_renames(text, ns, path)
        if updated != text:
            write_text(path, updated)
            print(f"updated {rel(path)}")

    for base in (MANAGER_JAVA, MANAGER_AIDL):
        candidates = sorted(
            base.joinpath(*OFFICIAL_NAMESPACE.split(".")).parents,
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for p in candidates:
            if p != base and p.is_relative_to(base) and p.exists() and not any(p.iterdir()):
                p.rmdir()

    print(f"moved {moved} path(s), rewrote sources to namespace {ns}")
    errors = verify_namespace(ns)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("namespace verified")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="show current DIY package, certificate, namespace and library configuration")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("check", help="verify package name, certificate, namespace, resources, hooks and CI are consistent")
    p.add_argument("--apk", nargs="+", help="also verify these manager APKs use strict v2 signing and carry no forbidden literals")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("cert-info", help="print KSU_NEXT_MANAGER_SIZE/HASH of a certificate or APK")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_cert_info)

    p = sub.add_parser("verify-namespace", help="verify Kotlin/AIDL/C++/manifest/resource namespace consistency")
    p.add_argument("--namespace", help="expected namespace (defaults to namespace in manager/app/build.gradle.kts)")
    p.set_defaults(func=cmd_verify_namespace)

    p = sub.add_parser("set-package", help="change the manager package name everywhere")
    p.add_argument("package")
    p.set_defaults(func=cmd_set_package)

    p = sub.add_parser("set-cert", help="trust a new signing certificate (PEM, DER or APK)")
    p.add_argument("cert")
    p.set_defaults(func=cmd_set_cert)

    p = sub.add_parser(
        "set-namespace",
        help="rename the Kotlin namespace, manifest component classes and packaged library names",
    )
    p.add_argument("namespace")
    p.set_defaults(func=cmd_set_namespace)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
