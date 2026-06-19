> Objective: ship a felt improvement daily · KR: kaizen-score trend up over 7d

### kaizen · day 8 · 2026-06-19-1 · 8 iters · 109.9m · [● green]

| kaizen-score | shipped | tests | tokens |
|---|---|---|---|
| **90** (+4) | 8 | +15 | 0k |

7-day score: `▁▃▆█`  🟢

**What changed today**
- plan_limits policy SSOT (AP-4.3) — _before:_ VALID_PLANS existed but no plan→quota policy anywhere → _after:_ jarvis_core/plan_limits.py: PLAN_LIMITS + pure exceeds(); studio/enterprise UNLIMITED (S2); 9 tests
- AP-1.0/1.1 doc-sync — _before:_ AP-1.0/1.1 marked [ ] though PR#0 IDOR + PR#1 RequestContext shipped → _after:_ [x] with verified code evidence; track roadmap matches SAAS §4.0
- /whoami surfaces plan limits — _before:_ /whoami returned plan only; plan_limits was dead code → _after:_ /whoami returns limits (UNLIMITED→null); policy is now a live consumer
- /v1 422 → OpenAI error envelope — _before:_ malformed /v1 body → FastAPI {detail:[...]}; openai SDK can't parse → _after:_ 422 → {error:{type:invalid_request_error,code:422}}
- /v1 streaming: no exception leak — _before:_ stream backend error yielded raw exc ([error: <exc>]) to client → _after:_ generic [stream error] + server-side log; no info-disclosure
- /v1 500 → OpenAI error envelope — _before:_ unhandled /v1 error → {detail:Internal Server Error} → _after:_ 500 → {error:{type:api_error,code:500}}, traceback logged not leaked
- /v1/models SDK-required created — _before:_ /v1/models objects lacked created → SDK client.models.list() fails validation → _after:_ every model carries created:int (full Model shape)
- /v1 maturity doc-sync (AB2/AB5) — _before:_ maturity section: 'немає responses/usage'; gaps AB2/AB5 still open → _after:_ compat 9/10; AB2 & AB5 closed (verified vs code)

**Risk / reverted**
- ⚠ (risk)
- ⚠ (risk)

_actions:_ See full report · Run again · Explain revert
