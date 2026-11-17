Code review of keycloak__keycloak__33832: `mattpocock-skills:code-review`, with both axes run inline and no sub-agents. I did not build or run anything (benchmark mode), so every claim below is reasoned. There are no Critical findings.

Base `10aca55523` to HEAD `79d11c4890` is one commit, signed off. Standards sources: `CONTRIBUTING.md`, `PR-CHECKLIST.md`, `docs/tests-development.md` (referenced). I did not fetch issue #33831, so the spec is only the commit title: "Add AuthzClientCryptoProvider to authz-client in keycloak main repository".

## Spec

The title is met. `AuthzClientCryptoProvider` is added and registered through `META-INF/services`. `AuthzClient.create(Configuration)` calls `CryptoIntegration.init`, and the other two `create()` overloads delegate to it, so every entry point is covered.

1. **`common/src/main/java/org/keycloak/common/crypto/CryptoIntegration.java:57-70` — Important — the fail-fast check for multiple crypto providers is gone, and the three real providers tie.**
   - **Claim:** `detectProvider` used to throw `IllegalStateException("Multiple crypto providers loaded ...")`. Now it sorts by `order()`, picks the first, and logs the rest at debug level.
   - **Evidence:**
     - `DefaultCryptoProvider` (`crypto/default/.../DefaultCryptoProvider.java:83`), `WildFlyElytronProvider` (`crypto/elytron/.../WildFlyElytronProvider.java:76`) and `FIPS1402Provider` (`crypto/fips1402/.../FIPS1402Provider.java:114`) all return `200`.
     - The sort is stable, so with Default and FIPS both on the classpath the ServiceLoader/classpath order decides the winner, with no error.
     - That can silently put a FIPS deployment on a non-FIPS provider. Today that misconfiguration fails at startup.
     - The Quarkus server is not affected: `KeycloakRecorder.java:214` sets the provider explicitly. Every caller of `CryptoIntegration.init(...)` is affected (adapters, the testsuite, the `services` tests, `KeycloakApplication`).
   - **Why it is in scope:** the commit title only needs the authz provider (order 100) to give way to a real one. Removing the conflict check for ties among real providers goes beyond that.
   - **Fix:** distinct orders, or keep the throw when the top two orders are equal.
   - Reasoned; no failing command without a classpath build.

2. **`common/src/main/java/org/keycloak/common/crypto/CryptoProvider.java:39-45` — Minor — new abstract method on an SPI loaded through ServiceLoader, with no docs or upgrade note.**
   - **Claim:** `int order();` has no default, so any external `CryptoProvider` implementation stops compiling, and fails at runtime with `AbstractMethodError` as soon as `detectProvider` calls `order()` while sorting.
   - **Evidence:**
     - `PR-CHECKLIST.md`: "Required documentation is included ... Including updates to release notes and upgrade guide if applicable."
     - `CONTRIBUTING.md` #8: "Includes documentation."
     - `grep -rl CryptoProvider docs` finds nothing.
   - A `default` method would avoid the break.

3. **`authz/client/src/test/java/org/keycloak/authorization/client/test/ECDSAAlgorithmTest.java:42,65-71` — Minor — the ES384 and ES512 tests never use their own curves.**
   - **Claim:** the key pair comes from `KeyPairGenerator.getInstance("EC").genKeyPair()`, which is the JDK default P-256 curve, for every algorithm.
   - **Effect:** r and s stay 32 bytes and the DER sequence stays under 128 bytes. The long-form length paths (`ASN1Encoder.writeLength`, `ASN1Decoder.readLength` when length > 127) and the full-width P-521 integers are never run.
   - **Also not tested:** the new ordering logic in `CryptoIntegration.detectProvider`. There is no test with several providers on the classpath.
   - **Standard:** `CONTRIBUTING.md` #7 "Includes functional/integration test"; `PR-CHECKLIST.md` "There is sufficient test coverage."
   - Reasoned.

## Standards

4. **Minor — whitespace-only reformatting of code the change does not otherwise touch.**
   - **Where:**
     - `common/src/main/java/org/keycloak/common/crypto/CryptoProvider.java:94`
     - `crypto/default/src/main/java/org/keycloak/crypto/def/DefaultCryptoProvider.java:186`
     - `crypto/fips1402/src/main/java/org/keycloak/crypto/fips/FIPS1402Provider.java:203, 208, 230, 234`
   - **Evidence:** the diff hunks only strip trailing whitespace. `CONTRIBUTING.md`: "Do not format or refactor code that is not directly related to your contribution." `PR-CHECKLIST.md`: "The PR does not contain changes not relevant to the GitHub Issue."

5. **`authz/client/pom.xml:67-71` — Minor — unused test dependency.**
   - **Claim:** `org.hamcrest:hamcrest` is added at test scope, but the only test uses nothing but `org.junit.Assert` and `org.junit.Test`.
   - **Evidence:** `grep -rn hamcrest authz/client/src/test` finds nothing. Same `PR-CHECKLIST.md` rule on irrelevant changes.

6. **Commit message — Minor — the issue-link format does not match the documented one.**
   - **Claim:** the message is "Add AuthzClientCryptoProvider ... repository\ncloses #33831". The issue link is lowercase and sits on the line right after the summary with no blank line between.
   - **Evidence:** `CONTRIBUTING.md` "Commit messages and issue linking" shows a separate trailing `Closes #1234` line and says "please only use the above formats" (`Closes`).
   - Sign-off is present.

## Summary

- **Spec:** 3 findings. The worst is #1: providers are now picked silently by order, and Default, Elytron and FIPS all tie at 200 (Important).
- **Standards:** 3 Minor findings. The worst is #4, the unrelated whitespace reformatting.

## Unreviewed files

None. All 12 files in the patch were read and checked against the surrounding source:
- `authz/client/pom.xml`
- `AuthzClient.java`
- `ASN1Decoder.java`
- `ASN1Encoder.java`
- `AuthzClientCryptoProvider.java`
- `META-INF/services/org.keycloak.common.crypto.CryptoProvider`
- `ECDSAAlgorithmTest.java`
- `CryptoIntegration.java`
- `CryptoProvider.java`
- `DefaultCryptoProvider.java`
- `WildFlyElytronProvider.java`
- `FIPS1402Provider.java`

Two limits:
- The ASN.1 encoder/decoder internals were checked only for correctness on the ES256/384/512 paths. They are new code, so no repo standard applies to them.
- Dead code, such as the discarded `ASN1Encoder.create().write(...)` calls at `AuthzClientCryptoProvider.java:114-115`, is left out as a general code smell, per the brief.
