# Reproducing the Android research

Research date: 2026-10-17. Target: `com.logitech.ueboom` 7.22.0.355,
version code 355. Extracted base APK SHA-256:
`018e9d6159311034327780480ee3798a7cdf31c5e7d174b6c496bf2254410e76`.

The actual APK was copied from the connected, ADB-authorized phone with REA
`pull-adb-package`. The extraction reported one base APK, 80,701,946 bytes,
complete coverage, and no failures. No app private data was extracted. No
speaker control commands were transmitted during this static investigation.

## Prerequisites

Use existing `adb`, a full JDK 17+ including `jdk.compiler`, Node.js compatible
with REA 6.5.0, npm, curl and Python 3. The research host had Node 22.23.3 and
OpenJDK 21.0.12.1. REA 6.5.0 requires Node `^22.19.0 || ^24.11.0 || >=26.0.0`.
Linux also needs procps-compatible `ps`. A GUI decompiler is unnecessary.

The [REA upstream project](https://github.com/morluto/rea) supplies the analysis
workflow and command interfaces. Its pinned Android engine is JADX headless MCP
0.7.1. These are local research dependencies, not dependencies of the future
Linux application. This workflow uses the CLI without modifying Codex settings.

From the repository root:

```bash
mkdir -p .local/tools .local/apks .local/evidence
npm install --prefix .local/tools --no-audit --no-fund rea-agents@6.5.0
curl -fL --retry 2 -o .local/tools/jadx-headless-mcp-0.7.1-all.jar \
  https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar
sha256sum .local/tools/jadx-headless-mcp-0.7.1-all.jar
```

The engine must hash to
`6e5eacf500b64292bfb73c49797c1958f6ee44646e43e868039ae7feb573ff75`.
`scripts/rea.sh` checks this before starting REA.

## Extract and inspect

Unlock the phone, enable USB debugging, and accept its computer authorization.
Use your device serial from `adb devices -l`:

```bash
scripts/rea.sh list-adb-devices --format json
scripts/rea.sh pull-adb-package YOUR_SERIAL com.logitech.ueboom \
  --output-directory "$PWD/.local/apks" --format json \
  > .local/evidence/apk-pull.json
scripts/rea.sh inspect-android-package \
  "$PWD/.local/apks/com.logitech.ueboom/base.apk" --format json \
  > .local/evidence/package.json
scripts/rea.sh search-android-classes \
  "$PWD/.local/apks/com.logitech.ueboom/base.apk" com.logitech.ue.centurion \
  --format json > .local/evidence/classes.json
```

Inspect exact classes to obtain method names and overload indices before asking
for methods. Example:

```bash
scripts/rea.sh inspect-android-class \
  "$PWD/.local/apks/com.logitech.ueboom/base.apk" \
  com.logitech.ue.centurion.legacy.spp.centurion.CenturionMessage --format json
scripts/rea.sh inspect-android-method \
  "$PWD/.local/apks/com.logitech.ueboom/base.apk" \
  com.logitech.ue.centurion.legacy.spp.centurion.CenturionMessage \
  buildCommandData --format json
scripts/rea.sh inspect-android-method \
  "$PWD/.local/apks/com.logitech.ueboom/base.apk" \
  com.logitech.ue.centurion.legacy.spp.centurion.CenturionCommand \
  '<clinit>' --format json > .local/evidence/commands.json
python3 scripts/command_catalog.py .local/evidence/commands.json \
  .local/reproduced-command-catalog.json
```

The catalogue exporter accepts direct CLI Evidence or REA service `value`
wrappers. The initial research also used REA's pinned internal service API in
local scratch scripts to reuse a provider across focused requests. That API is
not a public application dependency. APK upgrades can change classes, methods,
overload indices, and evidence identities; compare the APK digest first.

## Evidence handling and limits

Raw REA records, extracted APKs, downloads and temporary decompilation stay in
ignored `.local/`. The committed evidence index retains evidence identities and
selectors without phone serials, host paths or vendor source. Keep the ignored
files locally to inspect raw evidence; another laptop must extract its own APK.
Evidence IDs identify those local observations, not publicly hosted records.

JADX reported 17,343 classes and 3,404 resources. Static initializers fell back
to smali, which provided numeric constants; other selected methods generally
returned Java. Decompiled text is an interpretation, not original source or
runtime proof. APK signature verification was not performed. Dynamic loading,
reflection, firmware behavior and all model combinations remain outside this
pass. A receive-loop decompilation contains a suspicious reversed comparison;
do not reproduce it as a transport implementation without inspecting raw DEX
and validating with captured traffic.
