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

## The Frida route (needs root)

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
