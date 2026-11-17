I reviewed the patch with mattpocock-skills:code-review. As you asked, I did the review myself and did not spawn the skill's two sub-agents. The patch is one file, `pkg/api/webassets/webassets.go` (+14/-4), and I reviewed all of it. Every file in the patch was reviewed. I did not run any builds or tests, so every finding is reasoned.

The fix does what the commit message says. Every read and write of `entryPointAssetsCache` now holds `entryPointAssetsCacheMu`. That covers the read at lines 41-43 and the write and return at lines 69-70, which run under the write lock released by the defer. I checked all three callers: `pkg/api/index.go:82`, `pkg/api/frontendsettings.go:62` and `pkg/middleware/recovery.go:141`. None of them changes the shared `*dtos.EntryPointAssets` they get back. `SetContentDeliveryURL` only changes the new `result`, before it is stored in the cache.

## Standards
Sources checked: `CONTRIBUTING.md`, `contribute/create-pull-request.md`, `contribute/backend/style-guide.md`, `contribute/backend/recommended-practices.md`.

1. **Important — the bug fix ships without a regression test** (`pkg/api/webassets/webassets_test.go`, which the patch does not touch).
   - Claim: the repo requires bug-fix PRs to include a test that reproduces the bug. This patch adds none.
   - Evidence: `contribute/create-pull-request.md:28` says "To avoid regressions, the pull request should include tests that replicate the fixed bug." Line 22 says the PR should contain "necessary tests that verify the intended behavior."
   - The existing tests (`TestReadWebassets`, `TestReadWebassetsFromCDN`) never call `GetWebAssets` from more than one goroutine.
   - Test to add: call `GetWebAssets` from N goroutines against `testdata` and run it with `go test -race ./pkg/api/webassets/`. On the base commit it should report a race; on this patch it should pass.
   - Reasoned; not run.

2. **Minor — the commit subject has no Area prefix** (commit b1613e320a).
   - Claim: "fix data race in GetWebAssets" breaks the commit message format.
   - Evidence: `contribute/create-pull-request.md:94` says "Subject line must begin with the _area_ of the commit." Line 125 sets the PR title format as `<Area>: <Summary>`. Something like `Frontend: Fix data race in GetWebAssets` would fit; the area is my guess.
   - Grafana squashes on merge and uses the PR title as the subject, so this only matters if this commit becomes the PR title.

3. **Minor — the change grows global state instead of removing it** (`webassets.go:35-38`).
   - Claim: it adds a second package-level global (the mutex) next to the cached pointer. The added `// TODO: get rid of global state` admits the problem without fixing it.
   - Evidence: `style-guide.md:185-189` ("avoid using global variables") and `recommended-practices.md:46-54` ("100 - Global state", migrate to Wire/DI).
   - This is a judgement call. A narrow race fix is reasonable, and moving the cache onto a service is outside the scope of this commit.

Smell baseline: nothing to report. The new code is the standard lock-around-a-global pattern.

## Spec
There is no spec; I treated the commit message "fix data race in GetWebAssets" as the requirement.

- (a) Missing or partial: none. All access to the global goes through the lock.
- (b) Scope creep: none.
- (c) Implemented, but a weak spot:
  - **Minor — no re-check after taking the write lock** (`webassets.go:48-49`). When the cache is empty, several callers can all see `ret == nil`. Each then takes the exclusive lock in turn and reads `assets-manifest.json` again; with the CDN path enabled, that would be a network fetch each time. The result is still correct, only repeated work.
    - The fix is to re-check `entryPointAssetsCache != nil && cfg.Env != setting.Dev` after `Lock()`.
    - In Dev mode (`cfg.Env == setting.Dev`), every request now holds the exclusive lock while doing file I/O, so dev requests are serialized. This affects dev only.
    - Reasoned.

Summary: Standards has 3 findings; the worst is the missing regression test required by `create-pull-request.md:28` (Important). Spec has 1 finding; the worst is the repeated cold-start load from the missing re-check after `Lock()` (Minor).

Not checked: I did not run `go test -race`, and the test described above is not written yet.
