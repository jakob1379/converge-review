Seat: advisory, over-engineering only (ponytail:ponytail-review). I reviewed all 5 files in the patch.

What this change does: The resource server now runs `Init` once, eagerly, inside `NewResourceServer`, and the 12 per-request `s.Init(ctx)` guards are removed from Create, Update, Delete, Read, List, Watch, Search, History, Origin, IsHealthy, PutBlob and GetBlob. The search index is now built before the watcher starts. Bleve's cache lock now covers only the map write instead of the whole build, the trace contexts are passed through, and a postgres integration test is skipped.

Overall the patch is a net deletion and the right direction. What's left is leftover lazy-init scaffolding that the patch made redundant but didn't remove.

**Findings**

1. **The init error is logged twice** — `pkg/storage/unified/resource/server.go:258-262`, Minor (lean)
   - **Claim:** `NewResourceServer` logs `"error initializing resource server"` and then returns the error. `Init` already logs the same message with the same key at `server.go:313-315`, so one failure prints two identical lines.
   - **Evidence:** I read both sites. The message string and the `"error"` key are the same in both.
   - **Fix:** Drop the log in the constructor: `if err := s.Init(ctx); err != nil { return nil, err }`. That removes 2 lines.

2. **`sync.Once` and `initErr` gating are now dead scaffolding** — `server.go:286-289` (`once`, `initErr` fields), `293-318` (`Init`), `320-341` (`Stop` writes to `initErr`), Minor (lean, yagni)
   - **Claim:** These fields existed so that every handler could call `Init` lazily and safely, and so that `Stop` could make later calls fail through `initErr`. After this patch:
     - `Init` has exactly one caller, the constructor at `server.go:258`.
     - `*server` is unexported.
     - `Init` is not on the `ResourceServer` interface (`server.go:27-32`).
     - Nothing type-asserts it.
     - So the `once` guard can never be hit twice, and the `initErr` values that `Stop` sets ("service is stopping" / "service is stopped") are read only by `Stop`'s own return.
   - **Evidence:**
     - `grep -rn "\.Init(" pkg --include=*.go` finds only `server.go:258` for this type.
     - `grep -rn "initErr\|\.once\|\.Init(" pkg/storage/unified/resource/*_test.go` returns nothing.
     - `grep -rn "interface{ *Init" pkg` returns nothing.
   - **Fix:** Make `Init` a plain unexported `init(ctx) error` with sequential early returns: lifecycle hooks, then search, then watcher. Delete the `once` and `initErr` fields. Have `Stop` return the `lifecycle.Stop` error directly. That saves about 12-15 lines.
   - **Caveat for the correctness seats:** removing the per-request `Init` calls also removed the only way requests were rejected after `Stop`. If that rejection was intended, it is now silently gone. Either way, the `initErr` writes in `Stop` no longer enforce anything.

**Out-of-seat note (not over-engineering; flagged because the patch introduces it, reasoned rather than tested)**

- **Possible crash from an unlocked map read** — `pkg/storage/unified/resource/search.go:216` together with `pkg/storage/unified/search/bleve.go:144-153`, likely Important.
  - **Why:** The new log line calls `s.search.TotalDocs()`, which loops over `b.cache` without taking `cacheMu`. Line 216 runs after the event goroutine is started at `search.go:207-213`. That goroutine can call `handleEvent` → `getOrCreateIndex` → `BuildIndex`, which writes `b.cache[key]` under `cacheMu.Lock()` at `bleve.go:137-139`.
  - **Effect:** Go treats a map read and write at the same time as a fatal error ("concurrent map iteration and map write"), which would crash the server during startup.
  - **Fix:** Take `cacheMu.RLock()` inside `TotalDocs`.
  - **Not checked:** I did not run `go test -race`, per benchmark mode. A trigger needs a write event for a resource that has no index yet, arriving during the init window.

Verdict: Ship from the over-engineering seat. The two lean items are optional, and the out-of-seat race should go to the correctness reviewers.
Lean: about 15 lines could be removed.

**Unreviewed files:** none. All five files in the patch were reviewed:
- `pkg/server/module_server_test.go`
- `pkg/storage/unified/resource/search.go`
- `pkg/storage/unified/resource/server.go`
- `pkg/storage/unified/search/bleve.go`
- `pkg/storage/unified/sql/backend.go`

The test skip and the `ctx` propagation changes in `search.go` and `backend.go` have no over-engineering issues.

Not checked: no build, tests or race detector were run (benchmark mode). Load assumed: a multi-tenant Grafana server process with concurrent gRPC traffic.
