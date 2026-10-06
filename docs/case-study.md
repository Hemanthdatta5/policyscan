# Case study: PolicyScan vs. ToS;DR

Generated 2026-10-05 by `python -m ml.case_study`. Live scans, so results change as sites change.

- Sites attempted: 26; scanned successfully: 20; with a ToS;DR grade as well: 20.
- Spearman rank correlation between PolicyScan score and ToS;DR grade (A=5 .. E=1): **0.19**.

| Site | PolicyScan score | Rating | Undisclosed trackers | ToS;DR | Note |
| --- | --- | --- | --- | --- | --- |
| google.com | 5.6 | Fair | 0 | E | https://www.google.com/intl/en/policies/privacy/ |
| facebook.com |  |  |  | E | not scanned: could not find a privacy policy page; paste the policy text instead |
| x.com |  |  |  | E | not scanned: could not find a privacy policy page; paste the policy text instead |
| github.com | 8.1 | Good | 0 | D | https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement |
| reddit.com |  |  |  | D | not scanned: could not find a privacy policy page; paste the policy text instead |
| amazon.com | 4.4 | Poor | 7 | D | https://www.amazon.com/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ&ref_=footer_privacy |
| netflix.com | 7.0 | Fair | 0 | D | https://help.netflix.com/legal/privacy |
| spotify.com | 5.9 | Fair | 2 | E | https://www.spotify.com/us/legal/privacy-policy/ |
| duckduckgo.com | 7.8 | Fair | 0 | C | https://duckduckgo.com/privacy |
| microsoft.com | 5.3 | Fair | 6 | D | https://www.microsoft.com/en-us/privacy?icid=DSM_Footer_Company_Privacy |
| apple.com | 7.7 | Fair | 0 | C | https://www.apple.com/legal/privacy/ |
| linkedin.com |  |  |  | C | not scanned: could not find a privacy policy page; paste the policy text instead |
| pinterest.com |  |  |  | E | not scanned: could not find a privacy policy page; paste the policy text instead |
| tiktok.com | 6.9 | Fair | 0 | E | https://www.tiktok.com/privacy/overview/en |
| dropbox.com | 6.9 | Fair | 5 | D | https://www.dropbox.com/terms |
| mozilla.org | 7.3 | Fair | 0 | C | https://www.mozilla.org/nl/privacy/websites/ |
| proton.me | 8.4 | Good | 0 | D | https://proton.me/legal/privacy |
| zoom.us | 4.4 | Poor | 9 | D | https://www.zoom.com/en/trust/privacy/privacy-statement/ |
| slack.com | 4.4 | Poor | 5 | C | https://slack.com/trust/privacy/privacy-policy |
| medium.com |  |  |  | D | not scanned: could not find a privacy policy page; paste the policy text instead |
| twitch.tv | 7.4 | Fair | 2 | D | https://www.twitch.tv/privacy |
| bbc.com | 5.6 | Fair | 5 | D | https://www.bbc.com/pages/privacy-policy |
| theguardian.com | 4.4 | Poor | 10 | D | https://www.theguardian.com/info/privacy |
| nytimes.com | 6.7 | Fair | 0 | C | https://www.nytimes.com/privacy |
| stackoverflow.com | 5.6 | Fair | 6 | D | https://www.cloudflare.com/privacypolicy/ |
| ebay.com | 6.9 | Fair | 0 | D | https://www.ebay.com/splashui/captcha?ap=1&appName=orch&ru=https%3A%2F%2Fwww.ebay.com%2Fhelp%2Fpolicies%2Fmember-behaviour-policies%2Fuser-privacy-notice-privacy-policy%3Fid%3D4260&iid=28518f64-6ef7-47c8-b42b-7fc54feda203&iim=IMTI5LjS&iia=wIg5LjE4HB&iiz=barMS42Mg**NZJ |

## Reading this honestly

- ToS;DR grades a service's terms and policies by community-reviewed points; PolicyScan scores one privacy policy plus the trackers loaded on the home page. They measure related but different things, so only a rough agreement is expected.
- Sites that block automated requests, or whose policy is not on a discoverable page, are listed as not scanned rather than guessed.
- Tracker results are for the home page only, before and after clicking a cookie banner button; deeper pages may load more.
- Disclosure matching is by company name in the policy text, so a policy that only says "advertising partners" counts as not naming the tracker.

## Result (2026-10-05 run)

20 of 26 sites were scanned. The rank correlation with ToS;DR is weak (0.19), so on this sample PolicyScan does **not** track ToS;DR grades closely. Likely reasons, none yet tested:

- ToS;DR weighs terms of service and community-flagged practices; PolicyScan only reads the privacy policy, so a site with a readable privacy policy (GitHub, Proton) can score well while ToS;DR grades it lower.
- The rules layer is keyword-based and the hedge-word penalty is capped, so long policies are not penalized proportionally.
- Home-page trackers are only a slice of what a site does.
- Six sites (Facebook, X, Reddit, LinkedIn, Pinterest, and similar) block automated access and could not be scanned; no attempt was made to bypass their bot protection.

Next steps for the team: tune `app/core/scoring_config.py` against a hand-labelled set, add Tracker Radar for better entity matching, and re-run this study.
