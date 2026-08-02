# Release signing

This folder holds the Android signing key. **Its contents are git-ignored and must
stay that way** — `.jks`, `.keystore` and anything matching `*password*` are
excluded in `tools/.gitignore`.

```
pvzf-release.jks         the keystore (RSA 4096, valid ~30 years)
keystore-password.txt    the store and key password
```

Alias: `pvzf`

## Back this up somewhere off this machine

Android identifies an app by its signing key. If you lose the keystore you can
**never publish an update to this app again** — not a patched one, not a fixed
one. Every existing player would have to uninstall, which on Android deletes
their save, and then install a build signed with a new key.

Copy both files to a password manager or an encrypted backup now. Losing them is
not recoverable by any means.

## Using it

```bash
tools/.venv/Scripts/python.exe tools/android/build_apk.py \
    --apk APKs/<chinese>.apk --lang English --out dist \
    --compose-names --textures \
    --keystore tools/android/signing/pvzf-release.jks \
    --ks-alias pvzf --ks-pass "$(cat tools/android/signing/keystore-password.txt)" \
    --key-pass  "$(cat tools/android/signing/keystore-password.txt)"
```

Every build signed with this key installs over the previous one and keeps the
player's save. That property only holds if you never switch keys, which is the
whole reason the key was generated once, up front, rather than per release.

## If you ever publish through CI

Do not commit the keystore to get it onto a runner. Base64 it into an encrypted
repository secret and write it to disk during the job:

```yaml
- run: echo "${{ secrets.KEYSTORE_B64 }}" | base64 -d > release.jks
```
