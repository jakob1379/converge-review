Review of pinned.patch (base f3b74019 → head bb75657f). There was no spec, so I judged the patch against the security goal its own code and tests state: "Check that the authenticated GitHub user is the same as who installed the app." I loaded the superpowers:requesting-code-review skill but did not dispatch a subagent, as instructed. I ran no tests, so every claim below is reasoned from the source.

**Findings**

1. **src/sentry/integrations/github/integration.py:402 and :412 — Important.**
   - **Claim:** The OAuth `state` is `pipeline.signature`, which is a fixed value anyone can compute. It gives no CSRF protection, and an attacker can forge the authorize callback.
   - **Evidence:**
     - `src/sentry/pipeline/base.py:132-133` computes the signature as `md5_text(*[fqn of each view class])`. It is the same for every user and every session.
     - The tests hardcode it as `9cae5e88803f35ed7970fc131e6e65d3` in every test.
     - The house OAuth view does it properly: `src/sentry/identity/oauth2.py:245-252,325` uses `secrets.token_hex()`, binds it into pipeline state and compares against that.
     - Attack path: `OAuthLoginView` binds `installation_id` from `request.GET` on any leg (:397-399). A link such as `/extensions/github/setup/?code=<attacker code>&state=9cae…&installation_id=<attacker install>` opened by a victim who is partway through the install would bind the attacker's GitHub login and installation into the victim's pipeline. The user-match check then passes, and the victim's Sentry org gets linked to the attacker's installation. This needs the victim to be mid-pipeline.

2. **src/sentry/integrations/github/integration.py:481 — Important.**
   - **Claim:** The user-match check runs only when an `Integration` row already exists. When it does not, the code goes straight to `next_step()`. `build_integration` then fetches the installation with the app JWT, which works for any installation id, so the GitHub user who completed OAuth is never compared to the installer.
   - **Evidence:**
     - The `except Integration.DoesNotExist: return pipeline.next_step()` path has no `github_authenticated_user` comparison.
     - The `Integration` row is normally created by the installation webhook (`webhook.py:200-209`). Until that webhook is processed (it can be delayed, fail, or lose a race with the user's redirect), anyone who knows the installation id can claim the installation into their own org. That is the hole this patch is meant to close.

3. **src/sentry/integrations/github/integration.py:503 — Important.**
   - **Claim:** `integration.metadata["sender"]["login"]` raises `KeyError`, which becomes a 500, for any `Integration` without `sender` metadata. That covers the ordinary re-install path.
   - **Evidence:**
     - `sender` is only written by the installation webhook (`webhook.py:204`). Pipeline-created integrations skip it: `build_integration` uses `if state.get("sender")` (integration.py:376), and the pipeline never binds `sender`. Integrations created before sender storage existed don't have it either.
     - The comment at that branch, "OrganizationIntegration does not exist, but Integration does exist", describes exactly the case of an org that uninstalled (its `OrganizationIntegration` is deleted but the `Integration` row is kept) and is now reinstalling.
     - The repo already treats `sender` as optional elsewhere: `installation.py:44` has `if "sender" not in integration.metadata: return 404`.
     - Failing test to add (not run): create the `Integration` through `assert_setup_flow()`, delete only the `OrganizationIntegration`, then run init plus OAuth setup again. I expect a `KeyError`/500 rather than the error page or success.
     - The existing reinstall test (test_integration.py:360-366) deletes the `Integration` too, so it never reaches this branch.

4. **tests/sentry/integrations/github/test_integration.py:379-396 (`test_installation_not_found`) — Important.**
   - **Claim:** The test now passes for the wrong reason. It no longer covers the 404 "installation could not be found" path.
   - **Evidence:**
     - It sends `state=ddd023d87a913d5226e2a882c4c4cc05`, which differs from the fixed signature `9cae…`. The request is rejected by the state check at integration.py:412 before any installation lookup.
     - The 404 stub set up with `responses.replace` is never called.
     - The old assertion (`b"The GitHub installation could not be found."`) was replaced with the generic `b"Invalid installation request."`. The error path in `build_integration` at integration.py:355-356 is now untested.

5. **src/sentry/integrations/github/integration.py:423-434 — Minor.**
   - **Claim:** Network errors are not handled. `safe_urlopen` exceptions and `get_user_info`'s `resp.raise_for_status()` (identity/github/provider.py:16) are uncaught, so a GitHub outage or a revoked token gives a 500 instead of the `error()` page.
   - **Evidence:** Only `safe_urlread` and the parse step are inside the `try`.

6. **src/sentry/integrations/github/integration.py:408 — Minor.**
   - **Claim:** The authorize URL is built with an f-string, and `client_id`, `state` and `redirect_uri` are not URL-encoded.
   - **Evidence:** `redirect_uri` holds an absolute URL with `:` and `/`. It works today because the path has no `&`, `?` or `#`, but it is fragile. `oauth2.py:230-238` builds the same URL from a params dict with `urlencode`.

7. **src/sentry/integrations/github/integration.py:501-503 — Minor.**
   - **Claim:** The identity check compares GitHub `login` strings rather than the user id. A user who renames their GitHub account between installing and linking is wrongly rejected.
   - **Evidence:** The webhook stores `sender.id` (webhook.py:205), and `get_user_info` returns `id`, so the stable id is available on both sides.

8. **src/sentry/integrations/github/integration.py:493-497 — Minor.**
   - **Claim:** The first lookup at :475 has no status filter, but the second requires `status=ACTIVE`. A non-active `Integration` with no `OrganizationIntegration` now gets the generic "Invalid installation request" error. Before this patch it went on to `next_step`/`ensure_integration`.
   - **Evidence:** The two `Integration.objects.get` calls use different filters.

**Unreviewed files:** none. All three files were reviewed: src/sentry/integrations/github/integration.py, src/sentry/web/frontend/pipeline_advancer.py, and tests/sentry/integrations/github/test_integration.py. The pipeline_advancer.py change only inlines the `FORWARD_INSTALL_FOR` constant into `== "github"` and does not change behaviour.

Not checked: I did not verify that the hardcoded `HTTP_X_HUB_SIGNATURE` in `test_github_user_mismatch` matches the modified webhook body. I also did not verify that the GitHub App's configured callback URL accepts `/extensions/github/setup/` as `redirect_uri` in production or self-hosted setups. That second point is a deployment risk if the callback URL isn't configured.
