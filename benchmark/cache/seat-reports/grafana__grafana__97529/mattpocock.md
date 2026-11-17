Advisory review (Standards + intent; there is no spec) of change.patch, base 871af07203 to HEAD, 5 files. I followed mattpocock-skills:code-review and ran both axes myself. Standards sources read: contribute/backend/instrumentation.md, contribute/backend/style-guide.md, contribute/create-pull-request.md and contribute/style-guides/code-comments.md. The repo has no AGENTS.md or CLAUDE.md, and pkg/storage/unified/README.md says nothing about init. No builds or tests were run, so every finding below is reasoned, not reproduced.

## Spec (no spec; checked against the branch intent "unified-storage-dont-lazy-init")

1. **pkg/storage/unified/resource/server.go:320-340 (Stop) and 451-985 (all request handlers). Important.**
   - **Claim:** Removing the per-request `s.Init(ctx)` calls also removed the only thing that reads `s.initErr` after startup. Requests are no longer refused after `Stop`. Making init eager did not ask for this change.
   - **Evidence:**
     - `Stop` still sets `s.initErr = "service is stopping"`, then `"service is stopped"` or `"service stopeed with error"`.
     - Before the patch, `Create`, `Update`, `Delete`, `Read`, `List`, `Watch`, `Search`, `History`, `Origin`, `IsHealthy`, `PutBlob` and `GetBlob` all called `s.Init`. Because `once` had already run, that returned the current `initErr`, so a stopped server rejected requests.
     - `grep -n initErr pkg/storage/unified/resource/*.go` shows no reader outside `Init` and `Stop`. The writes in `Stop` are now dead.
     - `IsHealthy` (server.go:934) now reports healthy from diagnostics even while the server is stopping or stopped.
   - **How to check:** call `NewResourceServer`, then `Stop`, then `Read` or `IsHealthy`. Before the patch this returned an error; now it goes through to the backend. No such test exists (`grep 'service is stop' pkg --include=*_test.go` finds nothing).

2. **pkg/server/module_server_test.go:35-38. Important.**
   - **Claim:** The branch makes the storage-server target init eagerly and build the full search index. That startup now does more work, and this branch then skips the only integration test that checks the storage-server target comes up ("skipping - test not working with postgres in Drone. Works locally."). The skip hides what is most likely a startup-latency regression caused by this change.
   - **Evidence:**
     - The commit trail tries to work around it: 29db0d39b0 "wait 1 second before querying metrics", 1095580dce "try with big timeout, see if fixes CI", 45e0089891 "put delay back to 500 ms", then 6f4d70876a "skips postgres integration test… Will fix later."
     - contribute/create-pull-request.md:22 says "The pull request contains necessary tests that verify the intended behavior". Skipping a covering test goes against that.
   - **How to check:** `GRAFANA_TEST_DB=postgres go test ./pkg/server -run TestIntegrationWillRunInstrumentationServerWhenTargetHasNoHttpServer` now reports SKIP. The claim that it fails without the skip is reasoned from the commit history; I did not run it.

3. **pkg/storage/unified/resource/server.go:258-262. Minor.**
   - **Claim:** The new behaviour (`NewResourceServer` now returns lifecycle, search-index or watcher init errors at construction) has no test. That goes against create-pull-request.md:22.
   - **Evidence:** the patch touches no test file except the skip above. The existing server_test.go and watcher_test.go call `NewResourceServer`, but none checks the eager-init failure path.

## Standards

4. **pkg/storage/unified/resource/search.go:216. Minor (documented convention; the package already ignores it).**
   - **Claim:** The new log line `s.log.Info("search index initialized", "duration_secs", ..., "total_docs", ...)` breaks two rules in contribute/backend/instrumentation.md, section "Logs / Naming conventions":
     - "Start the log message with a capital letter".
     - "prefer using camelCase style when naming log keys", so `durationSecs` and `totalDocs`.
   - **Evidence:** the line itself. Every other `s.log.*` message in search.go and server.go is lowercase too, so this follows local habit, not the documented rule.

5. **pkg/storage/unified/resource/server.go:258-262 together with 313-314. Minor.**
   - **Claim:** The same error is logged twice with the identical message "error initializing resource server": once inside `Init` and again in `NewResourceServer` before returning it.
   - **Evidence:** instrumentation.md defines Error as "some operation failed… and the program didn't have a way to handle the error". Here the error is returned to the caller, so logging it at Error level twice is redundant. This is a judgement call.

6. **pkg/server/module_server_test.go:35, pkg/storage/unified/search/bleve.go:100. Minor.**
   - **Claim:** Two TODOs are added with no owner or issue link: "TODO - fix this test for postgres" and "TODO, check last RV…". In bleve.go the TODO is just a log line turned into a comment, with blank lines around it.
   - **Evidence:** no documented Grafana Go rule covers TODO format, so this is a judgement call. I flag it only because the test skip in finding 2 depends on this untracked TODO.

7. **Commit subjects. Minor.**
   - **Claim:** Commit subjects such as "dont lazy init unified storage" and "linter fix" do not meet contribute/create-pull-request.md:90-125 (Chris Beams style: capitalized imperative subject; PR title in the form `<Area>: <Summary>`).
   - **Evidence:** `git log 871af07203..HEAD --oneline`. This only matters if the PR title is not fixed, because commits are squashed.

**Positive compliance:**
- search.go:173 and 310, and sql/backend.go:126 now use `ctx, span := tracer.Start(...)` and pass the span context on. This matches the instrumentation.md trace example.
- search.go:280 replaces the `pkg/cmd/grafana-cli/logger` import with the component's structured logger, which is in line with instrumentation.md "Logs / Usage".

## Summary
- **Spec axis:** 3 findings. The worst is finding 1: after `Stop`, requests are no longer refused and `IsHealthy` still reports healthy.
- **Standards axis:** 4 findings, all Minor. The worst is the log message and key naming on search.go:216.

## Unreviewed files
None. I reviewed all 5 files in the patch: pkg/server/module_server_test.go, pkg/storage/unified/resource/search.go, pkg/storage/unified/resource/server.go, pkg/storage/unified/search/bleve.go and pkg/storage/unified/sql/backend.go.

I did not check the following, because they are outside an advisory standards and spec review:
- whether eager init at wire time (pkg/storage/unified/client.go, apistore/restoptions.go, registry/apis/dashboard/legacy_storage.go) runs before DB migrations;
- concurrency in bleve.go `BuildIndex` after its cache lock was narrowed;
- the existing data race in search.go `init` (`totalBatchesIndexed++` and the shared `err` written from errgroup goroutines).
