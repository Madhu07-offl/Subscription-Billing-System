#!/usr/bin/env bash
# concurrency.sh - proves next_document_number() never hands out the same number twice.
# Needs real parallel sessions, so it cannot live in smoke.sql (one transaction).
#   DATABASE_URL=postgresql://... bash database/tests/concurrency.sh
# Run after migrations. It restores the 'invoice' counter afterwards.
set -euo pipefail
: "${DATABASE_URL:?set DATABASE_URL}"
Q() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -qtA "$@"; }

saved=$(Q -c "select current_year || ',' || last_value from document_sequences where key = 'invoice'" || true)
restore() {
  if [ -n "${saved:-}" ]; then
    Q -c "update document_sequences set current_year = ${saved%,*}, last_value = ${saved#*,} where key = 'invoice'" >/dev/null
  else
    Q -c "update document_sequences set current_year = null, last_value = 0 where key = 'invoice'" >/dev/null
  fi
}
trap restore EXIT

# 1. 30 simultaneous callers must all get different numbers.
tmp=$(mktemp); trap 'rm -f "$tmp"; restore' EXIT
for _ in $(seq 1 30); do Q -c "select next_document_number('invoice')" >> "$tmp" & done
wait
total=$(wc -l < "$tmp"); uniq=$(sort -u "$tmp" | wc -l)
[ "$total" -eq 30 ] && [ "$uniq" -eq 30 ] || { echo "FAIL: $uniq distinct of $total numbers"; exit 1; }
echo "ok: 30 parallel calls -> 30 distinct numbers"

# 2. A second caller must WAIT for an open transaction (row lock), then get the next number.
a=$(mktemp); b=$(mktemp)
( Q <<SQL > "$a"
begin;
select next_document_number('invoice');
select pg_sleep(2);
commit;
SQL
) &
sleep 0.7
start=$(date +%s.%N)
Q -c "select next_document_number('invoice')" > "$b"
elapsed=$(awk -v s="$start" -v e="$(date +%s.%N)" 'BEGIN { printf "%.2f", e - s }')
wait
na=$(grep -m1 INV- "$a"); nb=$(grep -m1 INV- "$b")
[ "$na" != "$nb" ] || { echo "FAIL: both sessions got $na"; exit 1; }
awk -v t="$elapsed" 'BEGIN { exit !(t > 1.0) }' || { echo "FAIL: second caller did not wait for the lock ($elapsed s)"; exit 1; }
echo "ok: second caller blocked ${elapsed}s on the row lock; got $nb after $na"
rm -f "$a" "$b"
