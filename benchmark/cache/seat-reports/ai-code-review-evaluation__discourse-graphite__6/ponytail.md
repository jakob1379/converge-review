What this change does: The change moves the "website name" shown on a user's profile out of the Ember controller (which showed the bare host) and into a new server-side field, `UserSerializer#website_name`. When the website is on the same domain as the forum, a parent of it, or a sibling of it, the field holds the host plus the path. Otherwise it holds only the host. The template now reads `model.website_name`. The patch also fixes a wrong `@property` doc tag in `models/user.js.es6`.

I reviewed for over-engineering only, at the load of one serializer call per profile view. Speed does not matter at that load.

**Should fix**

1. **`include_website_name` is dead code, and the helper it reinvents already exists** (`app/serializers/user_serializer.rb:153-155`, Minor)
   - **What this is:** It looks like a conditional-include hook, meant to drop `website_name` from the JSON when the website is blank.
   - **Problem:** active_model_serializers 0.8.3 (Gemfile.lock:22) only calls `include_<attr>?`, with the question mark. Every other hook in this file has one (`include_email?`, `include_stats?`, and so on). This method is never called, so `website_name` is always sent, as `nil` when there is no website. The file already has `untrusted_attributes` (lines 25-33, 105-111). It generates `include_<attr>?` with a presence check and also hides the field when `scope.restrict_user_fields?(object)` is true. `:website` is already on that list. `:website_name` is not, so a restricted profile hides `website` but still sends `website_name`, which can carry the host and the full path. That leak is outside my lane, but this same fix closes it.
   - **Fix:** Delete lines 153-155 and add `:website_name` to the `untrusted_attributes` list at line 109. That is -3 lines, +1 line.
   - **If we skip it:** A hook that never runs stays in the file, and a restricted user's website still reaches the client through the new field.
   - **Evidence:** Reasoned. The attribute is declared at `user_serializer.rb:43`, and grep finds no caller of `include_website_name` without the `?`.

2. **The three-branch `website_name` is one boolean written the long way** (`app/serializers/user_serializer.rb:137-151`, Minor)
   - **What this is:** It decides whether to show "host" or "host + path".
   - **Problem:** It parses `URI(website.to_s)` three times and calls `discourse_host.split('.')` four times. It nests ternaries inside if/elsif/else, and every branch ends in the same two results. The branches never overlap. When the label counts are equal, `ends_with?(".host")` can only be true if the hosts are equal, and branch 1 already handles that. So the branches flatten to a single OR with the same behavior. The `# example.com == ...` comments exist only to explain the branching.
   - **Fix:** Parse once and use one condition:
     ```ruby
     def website_name
       uri = URI(website.to_s) rescue nil
       host = uri.try(:host)
       return if host.nil?
       dh = Discourse.current_hostname
       same_site = host == dh || dh.end_with?(".#{host}") ||
         (dh.count('.') > 1 && host.count('.') == dh.count('.') && host.split('.', 2).last == dh.split('.', 2).last)
       same_site ? host + uri.path : host
     end
     ```
     That is about 8 lines instead of 15.
   - **If we skip it:** The method works, but every later edit has to re-check three branches that do the same thing.

**Nice to have**

3. **The `"." << website_host` concatenation** (`user_serializer.rb:149`, Minor): `"." + website_host` or `".#{website_host}"` does the same job without an in-place append that makes a reader stop and check. This fix is already part of finding 2.

Removing `websiteName` from `controllers/user.js.es6` (-6 lines) is a good deletion. grep finds no other user of `websiteName` in app, lib, spec or plugins.

Verdict: Ship after 1. It is a 2-line change and also closes the restricted-profile leak. Finding 2 is optional cleanup.
Lean: -10 lines possible.
Files reviewed: all 5 in the patch (`controllers/user.js.es6`, `models/user.js.es6`, `templates/user/user.hbs`, `app/serializers/user_serializer.rb`, `spec/serializers/user_serializer_spec.rb`). None skipped.
Not checked: Outside my lane, the sibling-domain branch (www.example.com vs forum.example.com) has no spec, and the ported logic is not covered by any test. I did not run the specs.
