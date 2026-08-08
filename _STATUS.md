---
version: "M4.5"
badge: "M4.5 文書投入基盤 着工待ち"
next: "M4.5発令→実装（受信箱intake・文書スコープ選択・チャンクプロファイル）"
waiting_on: owner
---

# rag-system 現在地

更新: 2026-08-08 ／ 更新者: PM（クリーデ）

## 状態

- M1（ingest＋agent CLI）〜 M4（アドバイザー・速度改善・モデル拡充）完了。M3.1（回答メタデータフッター）含む
- 実測: R2問 268.6s(M3)→130.7s(M4)、51%短縮。アドバイザー守備範囲外裁定の実機動作確認済み
- M4.5指示書発行済み（docs/instructions/m4-5-instructions.md）。発注者の発令待ち

## 直近の経緯

- リポジトリを chromefixer-byte/jusetu-kogyo から misfortunemate-png/rag-system へ移管（2026-08-07。旧リポは発注者が削除）
- 開発はフラン（D:\AI\github\rag-system）に統一。業務側は運用専用フォークの方針

## 次の見通し

M4.5（文書投入基盤）→ M5（マルチ文書化・内線規程ingest・ハイブリッド検索。素材入手は発注者判断待ち）。全体は docs/roadmap-v1.md 参照
