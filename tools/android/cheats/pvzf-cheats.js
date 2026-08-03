/*
 * PvZ Fusion — cheat access on Android, via Frida (requires root).
 *
 *   frida -U -f com.LanPiaoPiao.PlantsVsZombiesRH -l pvzf-cheats.js
 *
 * The game already contains its cheats. `CheckCheatCodes` reads a `keyCodes`
 * array and fires them; on desktop you press Y / U / O / I. A phone has no
 * keyboard, so the code is present but unreachable.
 *
 * This does not add cheats. It gives the existing ones an input path, two ways:
 *
 *   1. key spoofing — `UnityEngine.Input.GetKeyDown` is hooked so a chosen key
 *      reads as pressed for exactly one frame, on demand. The game's own
 *      handler does everything else, so nothing here depends on knowing what
 *      the cheat code actually does internally.
 *   2. on-screen buttons — a small panel added to the game's own Activity that
 *      triggers (1). Added as a child of the existing view, not a system
 *      overlay, so it needs no extra permission.
 *
 * The APK is never modified: your installed build keeps its signature and its
 * save. Everything resolves by *name* through the IL2CPP C API that
 * `libil2cpp.so` exports, so a game update that moves every address should not
 * break this.
 */

'use strict';

const LIB = 'libil2cpp.so';

/* Unity's KeyCode enum matches ASCII for lowercase letters. */
const KEYS = {
  Y: { code: 121, label: 'Clear Zombies' },
  U: { code: 117, label: 'Clear Plants' },
  O: { code: 111, label: 'Random Seeds' },
  I: { code: 105, label: 'Place Vase' },
};

/* Everything prints with one tag so `adb logcat | grep pvzf` shows the whole
   startup path — which stage reached, which failed, and why. */
function log(msg) { console.log('[pvzf] ' + msg); }

let il2cpp = null;
let attached = false;
/* Keys queued to read as "pressed". Consumed by the first matching call. */
const oneShot = new Set();

/* ---------- IL2CPP C API ---------------------------------------------- */

function bind() {
  const need = (name, ret, args) => {
    const addr = Module.findExportByName(LIB, name);
    if (addr === null) throw new Error(`${LIB} does not export ${name}`);
    return new NativeFunction(addr, ret, args);
  };
  return {
    domain_get:             need('il2cpp_domain_get', 'pointer', []),
    domain_get_assemblies:  need('il2cpp_domain_get_assemblies', 'pointer', ['pointer', 'pointer']),
    assembly_get_image:     need('il2cpp_assembly_get_image', 'pointer', ['pointer']),
    image_get_class_count:  need('il2cpp_image_get_class_count', 'size_t', ['pointer']),
    image_get_class:        need('il2cpp_image_get_class', 'pointer', ['pointer', 'size_t']),
    class_get_name:         need('il2cpp_class_get_name', 'pointer', ['pointer']),
    class_get_namespace:    need('il2cpp_class_get_namespace', 'pointer', ['pointer']),
    class_get_methods:      need('il2cpp_class_get_methods', 'pointer', ['pointer', 'pointer']),
    class_get_fields:       need('il2cpp_class_get_fields', 'pointer', ['pointer', 'pointer']),
    method_get_name:        need('il2cpp_method_get_name', 'pointer', ['pointer']),
    method_get_param_count: need('il2cpp_method_get_param_count', 'uint32', ['pointer']),
    field_get_name:         need('il2cpp_field_get_name', 'pointer', ['pointer']),
    runtime_invoke:         need('il2cpp_runtime_invoke', 'pointer', ['pointer','pointer','pointer','pointer']),
    thread_attach:          need('il2cpp_thread_attach', 'pointer', ['pointer']),
    method_from_name:       need('il2cpp_class_get_method_from_name', 'pointer', ['pointer','pointer','int']),
  };
}

const str = p => (p.isNull() ? '' : p.readUtf8String());

/** Frida's thread is not a managed thread; calling in without attaching crashes. */
function attach() {
  if (!attached) { il2cpp.thread_attach(il2cpp.domain_get()); attached = true; }
}

function eachClass(visit) {
  const countBuf = Memory.alloc(Process.pointerSize);
  const assemblies = il2cpp.domain_get_assemblies(il2cpp.domain_get(), countBuf);
  const n = countBuf.readULong();
  for (let i = 0; i < n; i++) {
    const image = il2cpp.assembly_get_image(assemblies.add(i * Process.pointerSize).readPointer());
    if (image.isNull()) continue;
    const total = il2cpp.image_get_class_count(image);
    for (let c = 0; c < total; c++) {
      const klass = il2cpp.image_get_class(image, c);
      if (!klass.isNull() && visit(klass) === false) return;
    }
  }
}

function fullName(klass) {
  const ns = str(il2cpp.class_get_namespace(klass));
  return (ns ? ns + '.' : '') + str(il2cpp.class_get_name(klass));
}

function methodsOf(klass) {
  const iter = Memory.alloc(Process.pointerSize); iter.writePointer(NULL);
  const out = [];
  for (;;) {
    const m = il2cpp.class_get_methods(klass, iter);
    if (m.isNull()) break;
    out.push({ ptr: m, name: str(il2cpp.method_get_name(m)), argc: il2cpp.method_get_param_count(m) });
  }
  return out;
}

function fieldsOf(klass) {
  const iter = Memory.alloc(Process.pointerSize); iter.writePointer(NULL);
  const out = [];
  for (;;) {
    const f = il2cpp.class_get_fields(klass, iter);
    if (f.isNull()) break;
    out.push(str(il2cpp.field_get_name(f)));
  }
  return out;
}

function findClass(name) {
  let hit = null;
  eachClass(k => { if (fullName(k) === name) { hit = k; return false; } });
  return hit;
}

/* ---------- 1. key spoofing -------------------------------------------- */

/*
 * A MethodInfo begins with its native code pointer, so *MethodInfo is the
 * address to hook. Static methods are compiled as
 *   ret f(args..., const MethodInfo*)
 * so for GetKeyDown(KeyCode) the key arrives as args[0].
 */
function hookInput() {
  attach();
  const klass = findClass('UnityEngine.Input');
  if (klass === null) { console.log('[!] UnityEngine.Input not found'); return false; }

  let hooked = 0;
  for (const name of ['GetKeyDown', 'GetKeyUp', 'GetKey']) {
    const m = il2cpp.method_from_name(klass, Memory.allocUtf8String(name), 1);
    if (m.isNull()) continue;
    const code = m.readPointer();
    if (code.isNull()) continue;
    try {
      Interceptor.attach(code, {
        onEnter(args) { this.key = args[0].toInt32(); },
        onLeave(retval) {
          // GetKey is held-state; GetKeyDown/Up are edges. One frame is enough
          // for all three, and consuming the flag keeps it to a single press.
          if (oneShot.has(this.key)) { oneShot.delete(this.key); retval.replace(ptr(1)); }
        },
      });
      hooked++;
    } catch (e) {
      console.log(`[!] could not hook Input.${name}: ${e.message}`);
    }
  }
  console.log(hooked ? `[+] input hooked (${hooked} method(s))` : '[!] no input methods hooked');
  return hooked > 0;
}

/** Queue a single synthetic press, e.g. press('Y'). */
function press(key) {
  const k = KEYS[String(key).toUpperCase()];
  if (!k) { console.log(`[!] unknown key ${key}; known: ${Object.keys(KEYS).join(', ')}`); return; }
  oneShot.add(k.code);
  console.log(`[+] queued ${String(key).toUpperCase()} — ${k.label}`);
}

/* ---------- 2. on-screen buttons --------------------------------------- */

/*
 * Added to the Activity's own content view rather than as a system overlay, so
 * no SYSTEM_ALERT_WINDOW permission is involved.
 */
/* Registered once — Java.registerClass throws if the same name is used twice. */
let ClickListener = null;
function clickListenerFor(key) {
  if (ClickListener === null) {
    ClickListener = Java.registerClass({
      name: 'pvzf.CheatClick',
      implements: [Java.use('android.view.View$OnClickListener')],
      fields: { which: 'java.lang.String' },
      methods: { onClick(_v) { press(this.which.value); } },
    });
  }
  const l = ClickListener.$new();
  l.which.value = key;
  return l;
}

/**
 * Find the current Activity. `ActivityClientRecord.paused` does not exist on
 * every Android version, so fall back to "any activity we can see" rather than
 * failing outright.
 */
function currentActivity() {
  const ActivityThread = Java.use('android.app.ActivityThread');
  const records = ActivityThread.currentActivityThread().mActivities.value;
  const Record = Java.use('android.app.ActivityThread$ActivityClientRecord');
  let fallback = null;
  const it = records.values().iterator();
  while (it.hasNext()) {
    const rec = Java.cast(it.next(), Record);
    const activity = rec.activity.value;
    if (activity === null) continue;
    fallback = fallback || activity;
    try { if (!rec.paused.value) return activity; } catch (_) { return activity; }
  }
  return fallback;
}

function buildUI() {
  if (!Java.available) { log('Java runtime not available'); return; }
  Java.perform(() => {
    let activity;
    try {
      activity = currentActivity();
    } catch (e) { log(`activity lookup failed: ${e.message}`); return; }
    if (!activity) { log('no activity yet'); return; }
    log(`activity: ${activity.$className}`);

    const LinearLayout = Java.use('android.widget.LinearLayout');
    const Button = Java.use('android.widget.Button');
    const ViewGroupLP = Java.use('android.view.ViewGroup$LayoutParams');
    const Gravity = Java.use('android.view.Gravity');
    const FrameLP = Java.use('android.widget.FrameLayout$LayoutParams');
    const Color = Java.use('android.graphics.Color');

    Java.scheduleOnMainThread(() => {
      try {
        const panel = LinearLayout.$new(activity);
        panel.setOrientation(LinearLayout.VERTICAL.value);
        panel.setBackgroundColor(Color.argb(190, 0, 0, 0));
        // Unity renders into a SurfaceView; without an explicit Z the panel can
        // end up behind it on some devices.
        try { panel.setElevation(1000.0); } catch (_) {}

        for (const key of Object.keys(KEYS)) {
          const b = Button.$new(activity);
          b.setText(`${KEYS[key].label} (${key})`);
          b.setAllCaps(false);
          b.setOnClickListener(clickListenerFor(key));
          panel.addView(b, ViewGroupLP.$new(ViewGroupLP.WRAP_CONTENT.value,
                                            ViewGroupLP.WRAP_CONTENT.value));
        }

        const lp = FrameLP.$new(ViewGroupLP.WRAP_CONTENT.value, ViewGroupLP.WRAP_CONTENT.value);
        lp.gravity.value = Gravity.TOP.value | Gravity.START.value;
        // addContentView puts it in the content frame; the decor view sits above
        // everything the app draws, which is what we want over a SurfaceView.
        const decor = activity.getWindow().getDecorView();
        Java.cast(decor, Java.use('android.view.ViewGroup')).addView(panel, lp);
        panel.bringToFront();
        uiAdded = true;
        log('panel added');
      } catch (e) {
        log(`could not add panel: ${e.message}`);
      }
    });
  });
}

/* ---------- discovery (read-only) -------------------------------------- */

const WANTED = /^(CheckCheatCodes|CheatKey|CheatKeys|CheatShoot|CheatHard)$/;

function discover() {
  attach();
  const found = [];
  eachClass(klass => {
    const methods = methodsOf(klass);
    const hits = methods.filter(m => WANTED.test(m.name));
    if (hits.length) found.push({ name: fullName(klass), hits, methods, fields: fieldsOf(klass) });
  });
  if (!found.length) {
    console.log('[!] cheat methods not found yet — if the game is still loading, re-run discover()');
    return found;
  }
  for (const c of found) {
    console.log(`\n=== ${c.name} ===`);
    console.log('  cheat methods: ' + c.hits.map(m => `${m.name}/${m.argc}`).join(', '));
    console.log('  0-arg methods: ' + c.methods.filter(m => m.argc === 0).map(m => m.name).slice(0, 40).join(', '));
    console.log('  fields:        ' + c.fields.join(', '));
  }
  return found;
}

/** Invoke a zero-argument method by class and name. */
function call(className, methodName) {
  attach();
  const klass = findClass(className);
  if (klass === null) { console.log(`[!] class not found: ${className}`); return; }
  const m = il2cpp.method_from_name(klass, Memory.allocUtf8String(methodName), 0);
  if (m.isNull()) { console.log(`[!] ${className} has no 0-arg ${methodName}`); return; }
  const exc = Memory.alloc(Process.pointerSize); exc.writePointer(NULL);
  il2cpp.runtime_invoke(m, NULL, NULL, exc);
  console.log(exc.readPointer().isNull()
    ? `[+] called ${className}.${methodName}`
    : `[!] ${className}.${methodName} threw a managed exception`);
}

function dumpClass(needle) {
  attach();
  eachClass(klass => {
    const name = fullName(klass);
    if (!name.toLowerCase().includes(needle.toLowerCase())) return;
    console.log(`\n=== ${name} ===`);
    console.log('  methods: ' + methodsOf(klass).map(m => `${m.name}/${m.argc}`).join(', '));
    console.log('  fields:  ' + fieldsOf(klass).join(', '));
  });
}

/* ---------- entry ------------------------------------------------------ */

/*
 * Embedded in the APK (Frida Gadget) there is no REPL to type `ui()` into, so
 * the panel has to add itself. The Activity does not exist yet at library-load
 * time, so this retries until one is resumed and then stops.
 */
let uiAdded = false;
function autoUI(tries) {
  if (uiAdded) return;
  if (tries <= 0) { log('gave up adding the panel'); return; }
  // buildUI sets uiAdded only once the view is actually attached, so a failure
  // here keeps retrying instead of latching on a half-success.
  try { buildUI(); } catch (e) { log(`autoUI: ${e.message}`); }
  if (!uiAdded) setTimeout(() => autoUI(tries - 1), 1000);
}

function start() {
  log('script running — gadget loaded and config was read');
  try { il2cpp = bind(); } catch (e) { log(`FATAL binding libil2cpp: ${e.message}`); return; }
  log('libil2cpp bound');
  try { hookInput(); } catch (e) { log(`input hook failed: ${e.message}`); }
  discover();
  console.log('\nREPL:');
  console.log('  press("Y")   queue a keypress   (Y clear zombies, U clear plants, O seeds, I vase)');
  console.log('  ui()         add the on-screen panel (run once the game is in a level)');
  console.log('  discover()   re-scan            call(cls, m)   dumpClass(needle)');
  Object.assign(globalThis, { press, ui: buildUI, discover, call, dumpClass, KEYS });
  autoUI(120);  // harmless when driven from a REPL: ui() just happens on its own
}

// With -f the process spawns suspended and libil2cpp is not mapped yet.
(function waitForLib(tries) {
  if (Module.findBaseAddress(LIB) !== null) { start(); return; }
  if (tries <= 0) { log(`${LIB} never appeared — game may not have finished loading`); return; }
  setTimeout(() => waitForLib(tries - 1), 250);
})(160);
