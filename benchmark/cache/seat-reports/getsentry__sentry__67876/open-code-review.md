Review of pinned.patch (base f3b7401 → head bb75657). I ran OCR in delegation mode (`ocr delegate preview --from/--to`, then `ocr delegate rule`) and reviewed the code myself. I applied no fixes: your report-only instruction overrides the skill's auto-fix step.

Findings

1. src/sentry/integrations/github/integration.py:503 — **Important**. **Claim:** reinstalling an integration that has no `metadata["sender"]` crashes with a `KeyError`, which becomes an HTTP 500. The new user check reads `integration.metadata["sender"]["login"]` without checking that `sender` exists. It runs on the path "Integration exists, OrganizationIntegration does not", which is exactly the path for reinstalling an integration Sentry has already seen. **Evidence:**
   - `sender` is only written when the installation webhook builds the integration: `webhook.py:202-209` puts it into the state, and `build_integration` copies it at `integration.py:376-377`.
   - Integrations created through the UI pipeline don't get it. `IntegrationPipeline` calls `build_integration(self.state.data)` (`pipeline.py:93`), and that state has `installation_id` and `github_authenticated_user` but no `sender`.
   - Worse, `ensure_integration` (`pipeline.py:38-42`) calls `integration.update(metadata=...)` on rows that already exist. So even an integration the webhook created loses `sender` once the pipeline finishes.
   - The result: in practice, any integration installed through Sentry, plus every integration created before this patch, has no `sender`. After its OrganizationIntegration is removed, the next install attempt for that `installation_id` raises `KeyError`.
   - **Failing test** (reasoned, not run because benchmark mode forbids it): create `Integration(provider="github", external_id=installation_id, status=ACTIVE, metadata={})` with no OrganizationIntegration. Then GET the init path with `installation_id`, then the setup path with `code` and `state=<signature>`. Expected: the error page. Actual: `KeyError: 'sender'`.
   - Simplest fix: `integration.metadata.get("sender", {}).get("login")`, then treat a missing value as a failure. That still leaves the pipeline clobbering `metadata` as a separate problem.

2. src/sentry/integrations/github/integration.py:402, 412 — **Important** (security). **Claim:** the OAuth `state` parameter is the same for every user, so it gives no CSRF protection. **Evidence:**
   - `pipeline.signature` is `md5_text(*pipe_ids)`, where `pipe_ids` are the view class names (`pipeline/base.py:132-133`). It is identical for every user, session and org.
   - The patch's own tests hardcode it (`state=9cae5e88803f35ed7970fc131e6e65d3`) across different users and orgs.
   - The codebase's own `OAuth2LoginView` uses `secrets.token_hex()`, binds it to the pipeline state, and compares on callback (`identity/oauth2.py:245-252, 318-325`). This view drops that protection.
   - **Impact:** an attacker can send a victim who has a GitHub pipeline in progress to `/extensions/github/setup/?code=<attacker_code>&state=<constant>`. The victim's session then gets `github_authenticated_user` set to the attacker's GitHub login. That is a login-CSRF on the very identity this patch uses to authorise an install.
   - **Fix:** generate a random state, `bind_state` it, and compare against `fetch_state`.
   - Reasoned; no runnable test.

3. src/sentry/integrations/github/integration.py:423, 434 — **Minor**. **Claim:** failures while exchanging the token or fetching the user surface as 500s instead of the error page the patch adds. **Evidence:**
   - `get_user_info` calls `resp.raise_for_status()` (`identity/github/provider.py:16`), so a revoked token or a GitHub 4xx/5xx raises `HTTPError` uncaught.
   - `safe_urlopen` sits outside the `try`, so network errors propagate too.
   - Only `safe_urlread`/`parse_qsl` are guarded, and that guard is a broad `except Exception`.

4. src/sentry/integrations/github/integration.py:481 — **Minor**. **Claim:** the "authenticated user = installer" check is skipped whenever the Integration row doesn't exist yet. **Evidence:**
   - On `Integration.DoesNotExist` the view calls `pipeline.next_step()` without comparing `github_authenticated_user` to anything.
   - `build_integration` then resolves any `installation_id` of the app through the app JWT.
   - The protection therefore depends on the installation webhook arriving before the attacker's request. It narrows the hole rather than closing it.
   - Reasoned.

5. src/sentry/integrations/github/integration.py:408 — **Minor**. **Claim:** `redirect_uri` (and the other query values) go into the authorize URL without URL-encoding. **Evidence:** `absolute_uri(...)` is interpolated raw into the f-string. It works today only because the setup URL contains no `&`, `#` or `?`. `urlencode` would be the correct construction.

**No issues:** src/sentry/web/frontend/pipeline_advancer.py (+4/-7) only inlines the `FORWARD_INSTALL_FOR` constant as `provider_id == "github"`, and behaviour is unchanged.

Coverage: total_files 3, reviewed_files 2, skipped_files 1, coverage_rate 67%.

Unreviewed files
- tests/sentry/integrations/github/test_integration.py: OCR's default_path rule excluded it from review. I read it only as evidence: its hardcoded `state` value supports finding 2.

I did not run any tests (benchmark mode), so every finding is reasoned from the code.
