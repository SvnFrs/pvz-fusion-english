# Reaching the game's built-in cheats on Android

The game already ships its cheats. `global-metadata.dat` contains
`CheckCheatCodes`, `CheatKey`, `CheatKeys`, `CheatShoot` and `cheatIcon`, and the
on-screen messages they print are in every build:

```
 作弊模式已开启        Cheat Mode Enabled
 清除僵尸（Y）         Clear Zombies (Y)
 清除植物（U）         Clear Plants (U)
 随机卡槽（O）         Random Seedslot (O)
 右键放罐（I）         RMB for Vase (I)
```

They are **keyboard-bound**, not platform-gated — the only PC-only thing in the
build is a single level (`此关卡仅对PC端开放`). `CheckCheatCodes` reads a
`keyCodes` array, and a phone has no keys to read. The code is there; the input
path is not.

## No keyboard needed

A Bluetooth or OTG keyboard would reach these directly, but the script does the
same thing in software: it hooks `UnityEngine.Input.GetKeyDown` so a chosen key
reads as pressed for exactly one frame, on demand. The game's own handler runs
unchanged, so nothing depends on knowing what the cheat code does internally.

That also makes the first run the test. If `press("Y")` clears the zombies, the
cheat paths are live on Android. If it does nothing, they are compiled in but
inert, and no menu of any kind would have helped.

## Status: the embedded-gadget route does not work

**Tested on Android 13, rooted, and it fails.** Recorded here so nobody repeats
it. The APK builds, installs, and the game plays normally — but the script never
runs. It writes a log at parse time, and across two builds no log was ever
created.

What the symptoms prove, in order:

- the game **launches**, so `libfrida-gadget.so` loaded — a missing DT_NEEDED
  dependency would fail the linker and the app would not start;
- it does **not hang**, so Gadget read `libfrida-gadget.config.so` and entered
  script mode — with no config it defaults to Listen and blocks at startup;
- yet **no parse-time log appears**, so the script never executed.

The most likely cause is the loading method. With DT_NEEDED the gadget's
constructor runs *inside the dynamic linker*, holding the linker lock, while
Gadget's own startup spawns threads and calls `dlopen`. Every working Android
gadget injector instead adds `System.loadLibrary("frida-gadget")` from Java, by
rewriting `classes.dex` — which is also what
[SvnFrs/revenant](https://github.com/SvnFrs/revenant) does successfully on the
same device.

### What to use instead

**GameGuardian on the plain translated APK.** The game has **no anti-tamper** —
no root detection, no signature check, no integrity verification anywhere in the
metadata or identifier tables — so a memory editor works unimpeded and needs no
APK modification at all. Use
`dist/pvzf-<version>-english.apk`, not the `-cheats` build; both carry the same
signing key, so swapping between them keeps your save.

Rewriting `classes.dex` to call `System.loadLibrary` is the route that would
make the embedded approach work, and is the obvious next attempt if anyone wants
the button panel rather than a memory editor.

## The embedded-gadget build (kept for reference)

`embed_cheats.py` bakes the script into the APK, so there is nothing to attach
to and nothing to run each session — install it, launch the game, the buttons
are there.

```bash
tools/.venv/Scripts/python.exe tools/android/cheats/embed_cheats.py     --apk dist/pvzf-pvzrh3.8.1-english.apk --out dist     --keystore tools/android/signing/pvzf-release.jks --ks-alias pvzf     --ks-pass "$(cat tools/android/signing/keystore-password.txt)"     --key-pass "$(cat tools/android/signing/keystore-password.txt)"
```

Frida Gadget is the same engine as `frida-server`, but as an ordinary shared
library that runs a script from inside the app. Three files go in per ABI:

```
lib/<abi>/libfrida-gadget.so         the engine        (+18 MB total)
lib/<abi>/libfrida-gadget.config.so  run our script, don't open a socket
lib/<abi>/libpvzf-cheats.so          the script itself
```

The script is named `.so` deliberately: Android only unpacks `lib/<abi>/*.so`
onto disk, and Gadget resolves relative config paths next to itself, so naming
the JavaScript like a library is what puts it somewhere Gadget can read.

Loading is done by adding the gadget to `libmain.so`'s **DT_NEEDED** list, so the
dynamic linker pulls it in when Unity's own bootstrap library loads. That needs
no `classes.dex` edit and no manifest change — the game data, metadata and
manifest come out byte-identical to the translated APK.

> **This is the part most likely to be wrong.** As a link-time dependency, the
> gadget's constructor runs *inside the dynamic linker*, holding the linker
> lock, while Gadget's own startup spawns threads and calls `dlopen`. Every
> working Android gadget injector uses `System.loadLibrary("frida-gadget")` from
> Java instead — injected into `<clinit>` or `onCreate` by rewriting
> `classes.dex`. If the parse-time log below never appears, that is the reason,
> and DEX injection is the fix.

Signed with the same key, so it installs straight over your existing build and
keeps the save. Gadget in `script` mode never opens a port, and runs in the app's
own process, so **root is not required** for this route.

**Untested on hardware.** The structure is verified — both `libmain.so` files
still parse as valid ELF with the gadget first in DT_NEEDED — but if the gadget
fails to load, the linker aborts and the game will not start. Keep the plain
translated APK to reinstall over it if that happens.

## Driving it from a PC instead (needs root)

`frida-il2cpp-bridge` is not required — `libil2cpp.so` exports the whole IL2CPP C
API (all 18 functions this script needs), so `pvzf-cheats.js` is self-contained.

```bash
# on the phone, as root
./frida-server &

# on the PC
frida -U -f com.LanPiaoPiao.PlantsVsZombiesRH -l pvzf-cheats.js
```

On start it hooks input, then runs a **read-only discovery pass** that prints the
class owning `CheckCheatCodes`, its callable zero-argument methods and its
fields — real signatures, not assumed ones. Then, from the REPL:

```js
press("Y")     // clear zombies   (U plants, O random seeds, I place vase)
ui()           // add the on-screen button panel - run once you are in a level
discover()     // re-scan if the game was still loading
call(cls, m)   // invoke a 0-arg method      dumpClass(needle)
```

`ui()` adds buttons to the game's **own Activity view**, not a system overlay,
so `SYSTEM_ALERT_WINDOW` is never involved. Each button just queues a keypress,
so the panel is a front-end for the same path `press()` uses.

Everything resolves **by name**, never by address. A game update moves every
offset but rarely renames a method, so this should survive version bumps — which
is the main reason to prefer it over a byte-patched APK.

### Why this beats repacking

It does not touch the APK. Your installed build keeps its signature and its save
data. Repacking to inject a loader re-signs the APK, which means uninstalling,
which on Android means losing the save — the exact thing the permanent key in
[`../signing/`](../signing/) exists to avoid.

## How the on-screen panel works

`ui()` walks `ActivityThread` for the resumed Activity and calls
`addContentView` on it, adding a `LinearLayout` of buttons **inside the game's
own view hierarchy**. Because it is a child view and not a
`TYPE_APPLICATION_OVERLAY`, no `SYSTEM_ALERT_WINDOW` permission is needed —
which is worth knowing, since that permission is an appop and is awkward to grant
even with root.

Each button calls `press(key)`, so the panel and the REPL drive the same path.
Adding a cheat is one entry in the `KEYS` table at the top of the script.

The remaining option — rebinding an actual in-game button — means editing ARM64
code in `libil2cpp.so`, and is not worth it while the above works.

## What about ImGui, MelonLoader, or the prebuilt cheat APKs?

- **Magnetar Client** is a Windows .NET 6 assembly using HarmonyLib and
  Il2CppInterop — it patches methods at runtime and needs a .NET runtime that
  Android does not have. [LemonLoader](https://github.com/LemonLoader/MelonLoader)
  can supply one, but it re-signs the APK (save loss) and is unverified for this
  game.
- **Yurikia/PVZ-Menu-Cheat** edits another process's memory from outside — a
  Windows technique with no Android equivalent. Its releases also stop at game
  2.8.2.
- **Prebuilt "cheats" APKs** circulating for this game are binary-only, with no
  source and no licence. Running one is a supply-chain decision; redistributing
  one is also a licensing decision.

An ImGui menu is genuinely feasible — a native `.so` plus a custom `Application`
class to load it — but it is a multi-day C++/NDK project, and Frida gets you the
same access today without touching the APK.

## If the panel does not appear

**No PC or adb needed.** The script announces itself with a Toast and writes a
log you can open in any file manager:

```
/storage/emulated/0/Android/data/com.LanPiaoPiao.PlantsVsZombiesRH/files/pvzf-cheats.log
```

(falling back to `/data/data/<pkg>/files/` if the app cannot write to external
storage — readable with root).

Launch the game and watch for a Toast in the first few seconds:

| Toast | Meaning |
| --- | --- |
| **PvZF cheats: script loaded** | Injection worked. Anything wrong after this is the script, and the log says what. |
| **PvZF cheats: buttons ready** | The panel attached. If you still cannot see it, Unity is drawing over it — use the log's `press()` notes. |
| **PvZF cheats: panel failed — …** | The view could not attach; the message names the cause. |
| **no Toast at all** | The script never ran. The gadget did not load, or could not read the script. |

That last row is the important one — it separates "injection is broken" from
"the UI is broken", which are completely different problems.

### With adb, if you happen to have it

The script tags every line, so one command tells you which stage was reached:

```bash
adb logcat -c
# launch the game, then:
adb logcat | grep -iE "pvzf|frida|Gadget"
```

Read the first line you get:

| What you see | What it means |
| --- | --- |
| `[pvzf] script running` | Gadget loaded and found the script. Any failure after this is the script's, and the next lines say which. |
| `[pvzf] libil2cpp.so never appeared` | Gadget ran too early or the game did not finish loading. |
| `[pvzf] no activity yet` repeatedly | The Java side cannot see an Activity; the retry keeps going for two minutes. |
| `[pvzf] could not add panel: …` | The view failed to attach — the message names the cause. |
| Frida/Gadget lines but no `[pvzf]` | The gadget loaded but could not read the script. Most likely Android did not unpack `libpvzf-cheats.so`. |
| **nothing at all** | The gadget never loaded. Check it is on disk (below). |

Confirm what actually got unpacked onto the device:

```bash
adb shell run-as com.LanPiaoPiao.PlantsVsZombiesRH ls -l /data/data/com.LanPiaoPiao.PlantsVsZombiesRH/lib/
# or, with root:
adb shell su -c 'ls -l /data/app/*PlantsVsZombiesRH*/lib/arm64/'
```

You want three files there: `libfrida-gadget.so`, `libfrida-gadget.config.so`
and `libpvzf-cheats.so`. If the first two are present and the third is not,
Android declined to unpack a non-ELF file named `.so` — that is the known weak
point of this approach, and the fix is to keep the script somewhere else and
point `path` in the config at it (with root, `/data/local/tmp/pvzf-cheats.js`
works and only has to be pushed once).

A useful property while debugging: the game **starting normally at all** proves
the gadget loaded. If `libfrida-gadget.so` were missing or unloadable the
dynamic linker would fail `libmain.so`, and the game would not launch — and if
the gadget loaded but found no config it would default to Listen mode and hang
at startup waiting for a debugger. So a game that plays normally but shows no
panel means the gadget loaded *and* read the config; the problem is later.
