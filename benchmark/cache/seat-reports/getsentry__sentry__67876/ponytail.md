What this change does: it adds a GitHub OAuth login step (`OAuthLoginView`) in front of `GitHubInstallation`. When the GitHub installation already exists, the pipeline now checks that the logged-in GitHub user is the person who installed the app (`metadata["sender"]["login"]`). It also moves three copies of the error page into an `error()` helper, and inlines `FORWARD_INSTALL_FOR` in `pipeline_advancer.py`.

Load assumed: Sentry SaaS, so many users and orgs at once, and attackers who can send links to victims.

Findings

1. `src/sentry/integrations/github/integration.py:389-439` (the call site is `:344`). **Severity: Critical.**
   - **Claim:** `OAuthLoginView` hand-builds an OAuth2 flow (OAuth2 is the "log in with GitHub" handshake) that the repo already has. The copy dropped the safety parts of the original. The code even says so: "similar to OAuth2CallbackView.get_token_params" and "similar to OAuth2CallbackView.exchange_token".
   - **Evidence:**
     - The existing `OAuth2LoginView` / `OAuth2CallbackView` in `src/sentry/identity/oauth2.py:210-357` do this job. `NestedPipelineView` + `IdentityProviderPipeline` wrap them, and Slack (`src/sentry/integrations/slack/integration.py:126`) and VSTS (`src/sentry/integrations/vsts/integration.py:433`) use exactly this pattern. `GitHubIdentityProvider` (`src/sentry/identity/github/provider.py`) is already registered under key `"github"`.
     - What the copy lost:
       - (a) **State is a constant, not a per-session random value.** At `:402` and `:412` the OAuth `state` (the anti-forgery token) is `pipeline.signature`. `src/sentry/pipeline/base.py:132-133` computes that as the md5 of the view class names. So it is the same value for every user and every session, and anyone can compute it. The existing view uses `secrets.token_hex()` bound to the session. Proof: `python3 -c "import hashlib;h=hashlib.md5();[h.update(s.encode()) for s in ['sentry.integrations.github.integration.OAuthLoginView','sentry.integrations.github.integration.GitHubInstallation']];print(h.hexdigest())"` prints `9cae5e88803f35ed7970fc131e6e65d3`. That is the literal the tests hardcode across different users and orgs (`tests/sentry/integrations/github/test_integration.py:235,242,338,445,737`). Effect: the state check at `:412` cannot stop login CSRF (forged requests that log the victim in with someone else's account), and the new user-match check is meant to be a security gate.
       - (b) **`redirect_uri` is not URL-encoded.** At `:404-408` the authorize URL is built by f-string. The existing view uses `urlencode(params)` (`oauth2.py:250`).
       - (c) **Token-exchange errors are swallowed.** `except Exception: payload = {}` (`:424-428`) hides them. The existing code logs SSL, connection and decode errors separately.
   - **Fix:** delete `OAuthLoginView`, about 50 lines plus the 4 new imports. Return `[NestedPipelineView(bind_key="oauth", provider_key="github", pipeline_cls=IdentityProviderPipeline, config={...}), GitHubInstallation()]`. In `GitHubInstallation`, call `get_user_info(pipeline.fetch_state("oauth")["data"]["access_token"])`.
   - **Status:** the constant-state part is confirmed by the command above. That the replacement works end to end is reasoned, not run. The nested identity pipeline sends users back to `/extensions/default/setup/`, so check that the GitHub app's callback URL accepts it.

2. `src/sentry/integrations/github/integration.py:476-499`. **Severity: Minor.**
   - **Claim:** the same `Integration` row is fetched twice.
   - **Evidence:** `:478` runs `Integration.objects.get(external_id=installation_id)` inline and throws the object away. After the `installations_exist` check, `:494` runs `Integration.objects.get(external_id=installation_id, status=ObjectStatus.ACTIVE)` again.
   - **Fix:** keep the first result in a variable and check `integration.status != ObjectStatus.ACTIVE`. That saves one query and about 5 lines.

3. `src/sentry/integrations/github/integration.py:129-152` (the call sites are around `:468` and `:486`). **Severity: Minor.**
   - **Claim:** this one comes from the helper refactor and is outside the over-engineering scope. `error()` calls `_(error_short)` on a variable, while the call sites now pass plain string literals ("GitHub installation pending deletion.", "Github installed on another Sentry organization."). Before the patch these were `_("...")` literals, which `makemessages` (Django's tool that collects strings to translate) picks up. Now they are no longer extracted for translation.
   - **Fix:** wrap the literals at the call sites in `_()`, and drop the `_()` inside `error()`.
   - **Status:** reasoned.

4. `tests/sentry/integrations/github/test_integration.py:236-245, 335-340, 388-395, 434-447, 701-711, 733-740`. **Severity: Minor.**
   - **Claim:** the `setup_path + urlencode({"code": "12345678901234567890", "state": "<md5>"})` block is pasted 6 times. The magic state hash is hardcoded in each copy.
   - **Fix:** one fixture or helper that builds this URL. If finding 1 is fixed, the hardcoded constant-state literals have to go anyway, because the state becomes random.

Not a finding:
- `pipeline_advancer.py:37-45` inlines `FORWARD_INSTALL_FOR`. No other references exist, so it is a harmless simplification and has nothing to do with the feature.
- `get_document_origin` and `error()` replace three pasted copies of the error page. That is a net reduction.

Verdict: fix 1 first.
Lean: about -55 lines possible (finding 1 about -50, finding 2 about -5), plus about -40 test lines from finding 4.

Unreviewed files: none. All 3 files in the patch were reviewed: `src/sentry/integrations/github/integration.py`, `src/sentry/web/frontend/pipeline_advancer.py`, `tests/sentry/integrations/github/test_integration.py`.

Not checked: I ran no tests (benchmark mode). The `NestedPipelineView` replacement is reasoned, not executed. I did not check the GitHub app's registered OAuth callback URL.
