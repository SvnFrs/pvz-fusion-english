/*
 * PvZ Fusion — cheat access on Android, via Frida (requires root).
 *
 *   frida -U -f com.LanPiaoPiao.PlantsVsZombiesRH -l pvzf-cheats.js
 *
 * The game already contains its cheats — `CheckCheatCodes` reads a `keyCodes`
 * array and fires them. On desktop you press Y / U / O / I. A phone has no
 * keyboard, so the code is present but unreachable. This reaches it directly.
 *
 * Nothing here modifies the APK. The installed build keeps its signature and
 * your save, which is the main reason to prefer this over repacking.
 *
 * `libil2cpp.so` exports the full IL2CPP C API, so everything below is resolved
 * by *name* at runtime. That is deliberate: a game update moves every address
 * but rarely renames a method, so this should survive version bumps.
 *
 * Run it once and read the report before invoking anything — the discovery pass
 * is read-only, and it prints the real signatures rather than assuming them.
 */

'use strict';

const LIB = 'libil2cpp.so';

/* ---------- binding the IL2CPP C API ---------------------------------- */

let il2cpp = null;

function bind() {
  const need = (name, ret, args) => {
    const addr = Module.findExportByName(LIB, name);
    if (addr === null) throw new Error(`${LIB} does not export ${name}`);
    return new NativeFunction(addr, ret, args);
  };
  return {
    domain_get:            need('il2cpp_domain_get', 'pointer', []),
    domain_get_assemblies: need('il2cpp_domain_get_assemblies', 'pointer', ['pointer', 'pointer']),
    assembly_get_image:    need('il2cpp_assembly_get_image', 'pointer', ['pointer']),
    image_get_class_count: need('il2cpp_image_get_class_count', 'size_t', ['pointer']),
    image_get_class:       need('il2cpp_image_get_class', 'pointer', ['pointer', 'size_t']),
    class_get_name:        need('il2cpp_class_get_name', 'pointer', ['pointer']),
    class_get_namespace:   need('il2cpp_class_get_namespace', 'pointer', ['pointer']),
    class_get_methods:     need('il2cpp_class_get_methods', 'pointer', ['pointer', 'pointer']),
    class_get_fields:      need('il2cpp_class_get_fields', 'pointer', ['pointer', 'pointer']),
    method_get_name:       need('il2cpp_method_get_name', 'pointer', ['pointer']),
    method_get_param_count:need('il2cpp_method_get_param_count', 'uint32', ['pointer']),
    field_get_name:        need('il2cpp_field_get_name', 'pointer', ['pointer']),
    runtime_invoke:        need('il2cpp_runtime_invoke', 'pointer', ['pointer','pointer','pointer','pointer']),
    thread_attach:         need('il2cpp_thread_attach', 'pointer', ['pointer']),
    method_from_name:      need('il2cpp_class_get_method_from_name', 'pointer', ['pointer','pointer','int']),
  };
}

const str = p => (p.isNull() ? '<null>' : p.readUtf8String());

/** Frida's thread is not a managed thread; calling in without attaching crashes. */
let attached = false;
function attach() {
  if (attached) return;
  il2cpp.thread_attach(il2cpp.domain_get());
  attached = true;
}

/* ---------- walking the loaded assemblies ------------------------------ */

function eachClass(visit) {
  const countBuf = Memory.alloc(Process.pointerSize);
  const assemblies = il2cpp.domain_get_assemblies(il2cpp.domain_get(), countBuf);
  const n = countBuf.readULong();
  for (let i = 0; i < n; i++) {
    const image = il2cpp.assembly_get_image(assemblies.add(i * Process.pointerSize).readPointer());
    if (image.isNull()) continue;
    const classes = il2cpp.image_get_class_count(image);
    for (let c = 0; c < classes; c++) {
      const klass = il2cpp.image_get_class(image, c);
      if (!klass.isNull()) visit(klass);
    }
  }
}

function methodsOf(klass) {
  const iter = Memory.alloc(Process.pointerSize);
  iter.writePointer(NULL);
  const out = [];
  for (;;) {
    const m = il2cpp.class_get_methods(klass, iter);
    if (m.isNull()) break;
    out.push({ ptr: m, name: str(il2cpp.method_get_name(m)), argc: il2cpp.method_get_param_count(m) });
  }
  return out;
}

function fieldsOf(klass) {
  const iter = Memory.alloc(Process.pointerSize);
  iter.writePointer(NULL);
  const out = [];
  for (;;) {
    const f = il2cpp.class_get_fields(klass, iter);
    if (f.isNull()) break;
    out.push(str(il2cpp.field_get_name(f)));
  }
  return out;
}

/* ---------- discovery -------------------------------------------------- */

// Names found in this build's metadata. Anything matching gets reported.
const WANTED = /^(CheckCheatCodes|CheatKey|CheatKeys|CheatShoot|CheatHard)$/;

function discover() {
  attach();
  const found = [];
  eachClass(klass => {
    const methods = methodsOf(klass);
    const hits = methods.filter(m => WANTED.test(m.name));
    if (!hits.length) return;
    const ns = str(il2cpp.class_get_namespace(klass));
    found.push({
      klass,
      name: (ns && ns !== '<null>' ? ns + '.' : '') + str(il2cpp.class_get_name(klass)),
      hits,
      methods,
      fields: fieldsOf(klass),
    });
  });

  if (!found.length) {
    console.log('[!] No cheat methods found. Either the game has not finished');
    console.log('    loading (wait a few seconds and re-run discover()), or this');
    console.log('    build renamed them — run dumpClass("<partial name>") to look.');
    return found;
  }

  for (const c of found) {
    console.log(`\n=== ${c.name} ===`);
    console.log('  cheat methods:');
    for (const m of c.hits) console.log(`    ${m.name}(${m.argc} args)`);
    const interesting = c.methods.filter(m => m.argc === 0 && !WANTED.test(m.name)).slice(0, 40);
    console.log(`  other 0-arg methods (callable): ${interesting.map(m => m.name).join(', ')}`);
    console.log(`  fields: ${c.fields.join(', ')}`);
  }
  console.log('\nNext: call(<class>, <method>) to invoke a 0-arg method.');
  return found;
}

/** Invoke a zero-argument static/instance-less method by name. */
function call(className, methodName) {
  attach();
  let done = false;
  eachClass(klass => {
    if (done) return;
    const ns = str(il2cpp.class_get_namespace(klass));
    const full = (ns && ns !== '<null>' ? ns + '.' : '') + str(il2cpp.class_get_name(klass));
    if (full !== className) return;
    const m = il2cpp.method_from_name(klass, Memory.allocUtf8String(methodName), 0);
    if (m.isNull()) { console.log(`[!] ${className} has no 0-arg ${methodName}`); done = true; return; }
    const exc = Memory.alloc(Process.pointerSize);
    exc.writePointer(NULL);
    il2cpp.runtime_invoke(m, NULL, NULL, exc);
    console.log(exc.readPointer().isNull()
      ? `[+] called ${className}.${methodName}`
      : `[!] ${className}.${methodName} threw a managed exception`);
    done = true;
  });
  if (!done) console.log(`[!] class not found: ${className}`);
}

/** Print every method and field of classes whose name contains `needle`. */
function dumpClass(needle) {
  attach();
  eachClass(klass => {
    const name = str(il2cpp.class_get_name(klass));
    if (!name.toLowerCase().includes(needle.toLowerCase())) return;
    const ns = str(il2cpp.class_get_namespace(klass));
    console.log(`\n=== ${(ns && ns !== '<null>' ? ns + '.' : '') + name} ===`);
    console.log('  methods: ' + methodsOf(klass).map(m => `${m.name}/${m.argc}`).join(', '));
    console.log('  fields:  ' + fieldsOf(klass).join(', '));
  });
}

/* ---------- entry ------------------------------------------------------ */

function start() {
  il2cpp = bind();
  console.log('[*] libil2cpp bound. Running discovery…');
  discover();
  // Exposed so you can drive it from the Frida REPL:
  //   call("SomeClass", "CheckCheatCodes")
  //   dumpClass("Board")
  globalThis.discover = discover;
  globalThis.call = call;
  globalThis.dumpClass = dumpClass;
}

// With -f the process is spawned suspended and libil2cpp is not mapped yet.
(function waitForLib(tries) {
  if (Module.findBaseAddress(LIB) !== null) { start(); return; }
  if (tries <= 0) { console.log(`[!] ${LIB} never appeared`); return; }
  setTimeout(() => waitForLib(tries - 1), 250);
})(120);
