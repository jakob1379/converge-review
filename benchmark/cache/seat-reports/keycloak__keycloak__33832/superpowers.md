Review of keycloak__keycloak__33832 (base 10aca55..HEAD 79d11c4). I reviewed it myself, as instructed, using the requesting-code-review checklist. There was no spec, so I reviewed against the commit message: add `AuthzClientCryptoProvider` to authz-client and let it coexist with the real crypto providers.

The ECDSA codec is correct. I compiled the patch's `ASN1Encoder`/`ASN1Decoder` and the provider's two conversion functions in a standalone harness outside the repo. I checked 500 signatures each on P-256, P-384 and P-521 in both directions, against the JDK's `SHAxxxwithECDSAinP1363Format` as the reference. There were 0 failures, including the DER long-form length path that only P-521 reaches. The risk is in the changes to `common/`, not in the new provider.

## Findings

**1. common/src/main/java/org/keycloak/common/crypto/CryptoIntegration.java:57-71 — Important**
- **Claim:** The patch removes the fail-fast "Multiple crypto providers loaded" guard and replaces it with ordering, but all three real providers return the same order (200). When two of them are on the classpath, the choice is now silent and depends on classpath order.
- **Evidence:**
  - Ties are at `DefaultCryptoProvider.java:84`, `FIPS1402Provider.java:115` and `WildFlyElytronProvider.java:77`, all `return 200`.
  - `sorted(...)` is stable, so on a tie the `ServiceLoader` (classpath) order decides.
  - The losers are only logged at DEBUG.
  - Before the patch, having keycloak-crypto-default and keycloak-crypto-fips1402 together was a hard `IllegalStateException`. Now a FIPS deployment that picks up the non-FIPS jar by accident can quietly run on the non-FIPS BC provider.
- **Blast radius:** Quarkus is not affected, because it uses `CryptoIntegration.setProvider` (`KeycloakRecorder.java:214`). The paths that are affected are the ones that call `init`: `services/.../KeycloakApplication.java:89`, admin-cli `Globals.java:44`, and now `AuthzClient.create`.
- **Fix direction:** keep the guard when the top two providers have the same order, and only use ordering to break real differences (for example 100 vs 200).
- **Status:** Reasoned, not run. Failing test to add: put two providers with order 200 on the `ServiceLoader` path and assert that `CryptoIntegration.init` throws. It throws on the base commit and returns a provider on HEAD. No test covering the new selection logic exists in the patch.

**2. common/src/main/java/org/keycloak/common/crypto/CryptoProvider.java:44 — Important**
- **Claim:** `int order()` is added as an abstract method on a public interface in keycloak-common. Every CryptoProvider implementation outside this repo stops compiling.
- **Worse case:** an implementation that is already compiled and loaded through `ServiceLoader` hits `AbstractMethodError` inside `detectProvider` the moment the comparator calls `order()`, so `CryptoIntegration.init` crashes.
- **Context:** Inside the repo, every implementation was updated (`Fips1402StrictCryptoProvider` inherits it). keycloak-common is consumed outside this repo, for example by the separate keycloak-client authz-client, which is what this commit is mirroring.
- **Fix:** `default int order() { return 0; }` (or similar) avoids both problems.
- **Status:** Reasoned.

**3. authz/client/src/main/java/org/keycloak/authorization/client/AuthzClient.java:95 — Minor**
- **Claim:** `AuthzClient.create` now sets JVM-global crypto state, and the first caller wins (`init` does nothing once `cryptoProvider` is set).
- **Risk:** If `AuthzClient.class.getClassLoader()` can only see the stub provider, it fixes `AuthzClientCryptoProvider` as the provider for that JVM. That stub throws `UnsupportedOperationException` for almost everything. It also freezes `BouncyIntegration.PROVIDER` to the JDK keystore provider name. A later `KeycloakApplication` init in the same JVM, such as the embedded undertow testsuite, then does nothing.
- **Mitigation:** On the normal testsuite classpath, crypto-default (200) beats the stub (100), so I did not find a concrete failure.
- **Status:** Reasoned.

**4. authz/client/src/test/java/org/keycloak/authorization/client/test/ECDSAAlgorithmTest.java:42 — Minor**
- **Claim:** The test only checks that the provider's own conversions round-trip. It never checks the output against an independent encoding, and it uses one default-curve key for ES256, ES384 and ES512.
- **Effect:** With a P-256 key under ES512, the DER sequence is about 70 bytes, so the encoder and decoder long-form length branches are never exercised. A bug that is symmetric in both directions would also pass.
- **Mitigation:** My harness (P-256/384/521 with matching curves, checked against P1363) passes, so this is a gap in the test, not a bug. The fix is to generate the key per curve and verify the result with `SHAxxxwithECDSAinP1363Format`.

**5. authz/client/src/main/java/org/keycloak/authorization/client/util/crypto/AuthzClientCryptoProvider.java:114-115 — Minor**
- **Claim:** Dead code. Two `ASN1Encoder` instances are built and thrown away before the real encode at lines 117-121.

**6. common/src/main/java/org/keycloak/common/crypto/CryptoIntegration.java:65-69 — Minor**
- **Claim:** `logger.debugf(builder.toString())` passes text built at runtime as a format string, and the list ends with a stray ", ".
- **Fix:** Use `logger.debug`, or `debugf("Ignored crypto providers: %s", ...)` with a join.

**Behaviour that matches the stated intent:**
- Malformed DER makes `asn1derToConcatenatedRS` throw runtime exceptions (`NumberFormatException` for `30 04 02 00 02 00`). That direction only receives DER the JDK itself produced while signing.
- A short concatenated R‖S makes `concatenatedRSToASN1DER` throw `ArrayIndexOutOfBoundsException`. `ECDSASignatureVerifierContext.verify` catches `Exception` and wraps it in `VerificationException`, so untrusted JWS signatures are handled.
- `AsymmetricSignatureVerifierContext` tries the JDK `Signature` before `getSignature()`, so the stub that throws is not reached for ES*.

## Unreviewed files
I reviewed all 12 files in the patch. For the whitespace-only hunks in `DefaultCryptoProvider.java`, `FIPS1402Provider.java` and `CryptoProvider.java`, I only checked that they are whitespace and change nothing else.

I did not run the Maven build or the module's tests (benchmark mode). The codec claims rest on my standalone `javac` harness in the scratchpad, not on the repo build. Findings 1 to 3 are reasoned, not reproduced.
