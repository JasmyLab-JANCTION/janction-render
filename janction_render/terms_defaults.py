"""pricing.yaml の数字（生成物。手で直さない: tools/terms_sync.py --write が作り、--check が合っているかを見る）。

受付の設定を読めない手元の MCP（tooldocs.py）と、配布物の文の数字の出所。受付（server/billing.py）は env から読むが、
既定値はここと同じにしてある（tests/test_terms_sync.py が pricing.yaml の env_profile で全公開ページを描いて突き合わせる）。
"""
from __future__ import annotations

PUBLISHED_TERMS_DATE = "2026-10-26"
CURRENCY = "JPY"
YEN_PER_GPU_SECOND = 0.1
PRICING_VERSION = "2026-10-08"
PAID_SINCE = "2026-10-08"
WELCOME_MODEL = "card"
WELCOME_CARDLESS_YEN = 100
WELCOME_CARD_BONUS_YEN = 400
WELCOME_TOTAL_YEN = 500
WELCOME_DAYS = 14
WELCOME_NETWORK_DAYS = 30
PREVIEW_FREE_SECONDS_PER_DAY = 120
PREVIEW_FREE_MINUTES_PER_DAY = 2
FRAMES_PER_PART = 240
MAX_FRAMES_PER_INSTRUCTION = 3000
FREE_RESOLUTION = "1920x1080"
PREPAID_RESOLUTION = "3840x2160"
MAX_JOB_GPU_HOURS = 10
MIN_TOPUP_YEN = 100
TOPUP_STEP_YEN = 100
TOPUP_PACKS_YEN = [100, 500, 2000, 5000, 10000]
TOPUP_PACK_CREDIT_YEN = [100, 500, 2200, 5750, 12000]
FIRST_TOPUP_MULTIPLIER = 1.5
FIRST_TOPUP_BONUS_CAP_YEN = 500
RETENTION_HOURS = 24
PAID_RETENTION_DAYS = 7
PAID_MIN_YEN = 500
SPEND_CAP_JOB_YEN = 100000
SPEND_CAP_DAY_YEN = 100000
SPEND_CAP_HARD_MAX_YEN = 100000
MONTHLY_PLANS = [{'id': 'starter', 'name': 'Starter', 'price_yen': 2980, 'credit_yen': 3500}, {'id': 'pro', 'name': 'Pro', 'price_yen': 9800, 'credit_yen': 12000}]
# 公開物に 1 件でもあれば CI が落ちる言い方（正規表現、大文字小文字を区別しない）と、その理由
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ('free[ -]beta', '無料ベータは 2026-10-08 に終わった'),
    ('無料ベータ', '同上'),
    ('\\b10 GPU-?minutes\\b', '1 日 10 GPU 分の無料枠は 10/8 で終わった（今は試し描き 2 GPU 分）'),
    ('1 ?日 ?10 ?分|毎日 10 GPU 分|1 日 10 GPU 分', '同上（日本語）'),
    ('\\b500 JPY welcome\\b', 'network の形の額。今は 100 円（カード不要）+ 400 円（カード登録）、最大 500 円と言う'),
    ('(?<!最大 )(?<!最大)500 円分?のようこそ', '同上（日本語。「最大 500 円分のようこそクレジット」は可）'),
    ('5,000 GPU[- ]秒|5,000 GPU-seconds', '500 円分＝5,000 GPU 秒は network の形'),
    ('\\bfrom 500 JPY\\b|500 円から', '最低チャージ額は 100 円'),
    ('\\bminimum 500\\b|最低 ?500 ?円|最低チャージ額?は ?500', '最低チャージ額は 100 円（10/29: MCP の billing の topup_yen の説明に残り、Glama がそれを写していた）'),
    ('\\b(up to|at most|max(imum)?) 240 frames\\b|240 frames (per|a) job|240 コマまで|最大 240 コマ|1 回 240 コマ', '240 は 1 部分の大きさ。上限は 1 回の指示で 3,000 コマ'),
    ('\\b1,000 frames per\\b|1,000 コマまで', '1,000 コマの上限は 10/13 までの値'),
    ('Blender 5\\.0 only|5\\.0 だけ', '4.2 / 4.5 / 5.0 を受ける'),
    ('3,?000 JPY (per|a) (render )?(request|job)|(per-job|per job|per-request) cap[^.]{0,20}3,?000 JPY|3,?000 JPY by default|1 依頼 ?3,?000 ?円|既定 ?3,?000 ?円', '既定の 1 依頼の上限は 2026-11-02 に撤回した（今は既定なし、鍵ごとに自分で決める）'),
    ('10,?000 JPY (per|a) day by default|(per-day|per day) cap[^.]{0,20}10,?000 JPY|1 日 ?10,?000 ?円の上限', '既定の 1 日の上限も 2026-11-02 に撤回した（オートチャージの月 10,000 円は別の話）'),
]
# これらの数字を受付で実現する環境変数（gpu004 の env/server.env と同じであること）
ENV_PROFILE: dict[str, str] = {
    'JR_WELCOME_MODEL': 'card',
    'JR_WELCOME_SECONDS_CARDLESS': '1000',
    'JR_WELCOME_CARD_BONUS_SECONDS': '4000',
    'JR_WELCOME_DAYS': '14',
    'JR_WELCOME_NETWORK_DAYS': '30',
    'JR_FREE_PREVIEW_SECONDS_PER_DAY': '120',
    'JR_YEN_PER_GPU_SECOND': '0.1',
    'JR_FREE_MAX_FRAMES': '240',
    'JR_MAX_FRAMES_PER_INSTRUCTION': '3000',
    'JR_TOPUP_SHORTFALL': '1',
    'JR_TOPUP_SHORTFALL_MIN_YEN': '100',
    'JR_TTL_HOURS': '24',
    'JR_PAID_TTL_HOURS': '168',
    'JR_PAID_MIN_YEN': '500',
    'JR_SPEND_CAP_PER_JOB_YEN': '100000',
    'JR_SPEND_CAP_PER_KEY_PER_DAY_YEN': '100000',
}
