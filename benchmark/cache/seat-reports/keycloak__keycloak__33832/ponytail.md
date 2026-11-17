## Over-engineering review: keycloak PR 33832 (AuthzClientCryptoProvider)

**What this change does:** It adds a small crypto provider for authz-client that uses only the JDK, so the client works without BouncyCastle or Elytron. It includes a hand-written DER encoder and decoder for ECDSA signatures (DER is the binary format for signatures). It also adds `int order()` to the `CryptoProvider` interface, and `CryptoIntegration` now picks the provider with the highest order instead of throwing when it finds more than one.

The commit message asks for the provider, so I accept that it exists. Writing the DER code by hand is justified: the JDK has no public DER API, and this module deliberately avoids BC and Elytron. Everything below is about trimming. I found nothing Critical or Important in my lane (over-engineering).

### Findings

1. **`authz/client/src/main/java/org/keycloak/authorization/client/util/crypto/AuthzClientCryptoProvider.java:114-115`: Minor. Two lines do work and throw it away.**
   - **Claim:** `ASN1Encoder.create().write(rBigInteger);` and `ASN1Encoder.create().write(sBigInteger);` build encoders and then discard them. Lines 117-121 encode r and s again, and only that result is returned.
   - **Fix:** delete both lines. Nothing else changes (-2 lines).

2. **`common/src/main/java/org/keycloak/common/crypto/CryptoProvider.java:39-44`, plus `crypto/default/.../DefaultCryptoProvider.java:82-85`, `crypto/elytron/.../WildFlyElytronProvider.java:75-78`, `crypto/fips1402/.../FIPS1402Provider.java:113-116`: Minor. `order()` is abstract, so the same override is pasted three times.**
   - **Claim:** All three main providers return the same `200`. Only `AuthzClientCryptoProvider` needs a different value.
   - **Fix:** declare `default int order() { return 200; }` in the interface, keep the override only in `AuthzClientCryptoProvider`, and delete the other three (about -12 lines).
   - **Extra benefit:** with a default, a third-party `CryptoProvider` built against the old interface keeps working. As written, it would throw `AbstractMethodError` when `detectProvider` sorts by `order()`. This is reasoned, not run.

3. **`common/src/main/java/org/keycloak/common/crypto/CryptoIntegration.java:64-70`: Minor. A hand-built `StringBuilder` loop for one debug line.**
   - **Claim:** The loop adds a trailing ", ". It also passes a ready-built string to `debugf` as the format string, so a `%` in a class name would be misread.
   - **Fix:** one line does the same job: `logger.debugf("Ignored crypto providers: %s", foundProviders.subList(1, foundProviders.size()));`. Use `.stream().map(p -> p.getClass().getName())` if you want class names instead of `toString()` (-6 lines).

4. **`authz/client/src/main/java/org/keycloak/authorization/client/util/crypto/ASN1Decoder.java:93-124` and `:133-135`: Minor. General-purpose decoding that this decoder never needs.**
   - **Claim:** It handles high-tag-number tags and indefinite-length encoding, which looks copied from a full BouncyCastle-style parser. Its only production caller is `ECDSASignatureSignerContext` (`core/src/main/java/org/keycloak/crypto/ECDSASignatureSignerContext.java:33`). That caller passes the JDK's own `Signature.sign()` output, which is always tag 0x30 holding two 0x02 integers, in DER. DER never uses indefinite length.
   - **Side effect:** the indefinite-length branch returns `-1`. `readInteger` would then call `new byte[-1]` and throw `NegativeArraySizeException`, not `IOException`. So the "extra safety" code adds a crash path.
   - **Fix:** use `int tagNo = tag & 0x1f;` and reject any length byte with the high bit set beyond what the size check allows. This is about -25 lines.

5. **`authz/client/.../AuthzClientCryptoProvider.java:151-163` (`integerToBytes`) and the `concatenatedRSToASN1DER` body: Minor. The r/s byte handling is a near-copy of `crypto/elytron/src/main/java/org/keycloak/crypto/elytron/ElytronECDSACryptoProvider.java` (`concatenatedRSToASN1DER`, `convertToBytes`).**
   - **Claim:** The same padding and trimming logic now lives in at least two places, and BC has a third copy.
   - **Fix:** none needed now. It could only be shared through `keycloak-common`, and these modules deliberately share no dependencies. I note it only because a fix to one copy will not reach the others.

6. **`authz/client/pom.xml:15-19`: Minor. The `org.hamcrest:hamcrest` test dependency is unused.**
   - **Claim:** `ECDSAAlgorithmTest` imports only `org.junit.Assert` and `org.junit.Test`.
   - **Fix:** delete the dependency (-5 lines). This matches the pattern in `crypto/default/pom.xml`, so it is low priority.

7. **`ASN1Encoder.java:38-44` and `ASN1Decoder.java:39-47`: Minor. Each class has both a constructor and a static `create()` that only calls it.**
   - **Claim:** These are package-private classes with one caller. The factories add nothing over `new`.
   - **Fix:** use `new ASN1Encoder()` / `new ASN1Decoder(bytes)` and drop the factories (-6 lines).

8. **Whitespace-only hunks in `CryptoProvider.java:94`, `DefaultCryptoProvider.java:186`, `FIPS1402Provider.java:203,208,230,235`: Minor. Diff noise unrelated to the feature.**
   - **Fix:** leave them out. This is not a code issue.

**Context, not a finding:** the authz-client main code never signs or verifies with ECDSA. `TokenCallable` only calls `JWSInput.getContent()`. This module's pom also describes it as testsuite-only, and in the testsuite `DefaultCryptoProvider` (order 200) always wins over the new provider. So in this repository the ECDSA code is only exercised by its own unit test. The value of the change is matching the standalone `keycloak-authz-client`, which the commit message asks for.

Verdict: Ship. Nothing here blocks the merge.
Lean: about -55 lines possible (items 1-4, 6, 7).

### Unreviewed files
I reviewed all 12 files in the patch for over-engineering. I did not review correctness, security or load beyond the notes above, because that is outside this seat's lane. Nothing was built or run: the claim in item 2 about third-party providers and the crash path in item 4 are reasoned from the code, not tested.
