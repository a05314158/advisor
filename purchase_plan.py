"""Allocate whole purchases across cards with a shared monthly limit per card."""

MAX_PURCHASES = 8


def allocate_purchases(matches, caps):
    """Return the best allocation and the sequential best-card baseline."""
    offers = [{item['cardId']: item for item in row if item['cashbackKopecks'] > 0} for row in matches]
    cards = sorted({card for row in offers for card in row})
    balances = {}
    for card in cards:
        cap, used = caps.get(card, (None, None))
        if cap is not None:
            balances[card] = max(0, cap - (used or 0))

    def payout(row, card, remaining):
        value = row[card]['cashbackKopecks']
        return min(value, remaining[card]) if card in remaining else value

    def simulate(assignments=None):
        remaining = balances.copy()
        entries = []
        for index, row in enumerate(offers):
            card = (min(row, key=lambda key: (-payout(row, key, remaining), key), default=None)
                    if assignments is None else assignments[index])
            value = payout(row, card, remaining) if card is not None else 0
            if card in remaining:
                remaining[card] -= value
            match = row[card] if value else {}
            entries.append(dict(cardId=match.get('cardId'), cardName=match.get('cardName'),
                                bankName=match.get('bankName'), cashbackKopecks=value))
        return dict(totalKopecks=sum(entry['cashbackKopecks'] for entry in entries), purchases=entries)

    sequential = simulate()
    # One bit per purchase. For each card, try every disjoint subset of purchases.
    # Its total payout is the sum of those purchases, clipped once by the shared cap.
    all_purchases = (1 << len(offers)) - 1
    best = {0: (0, (None,) * len(offers))}
    for card in cards:
        values = [row.get(card, {}).get('cashbackKopecks', 0) for row in offers]
        eligible = sum(1 << index for index, value in enumerate(values) if value)
        subset_totals = {0: 0}
        subset = eligible
        while subset:
            subset_totals[subset] = sum(value for index, value in enumerate(values) if subset & (1 << index))
            subset = (subset - 1) & eligible
        next_best = best.copy()
        for assigned, (total, allocation) in best.items():
            available = eligible & (all_purchases ^ assigned)
            subset = available
            while subset:
                combined = total + min(subset_totals[subset], balances.get(card, subset_totals[subset]))
                mask = assigned | subset
                if combined > next_best.get(mask, (-1, ()))[0]:
                    next_best[mask] = (combined, tuple(card if subset & (1 << i) else previous
                                                       for i, previous in enumerate(allocation)))
                subset = (subset - 1) & available
        best = next_best

    total, allocation = max(best.values(), key=lambda state: state[0])
    optimized = simulate(allocation) if total > sequential['totalKopecks'] else sequential
    unknown = [dict(cardId=card, cardName=next(row[card]['cardName'] for row in offers if card in row))
               for card in balances if caps[card][1] is None]
    explanation = explain_plan(optimized, sequential, balances)
    return dict(optimized=optimized, sequential=sequential, assumedFullCardIds=[card['cardId'] for card in unknown],
                assumedFullCards=unknown, explanation=explanation, gainKopecks=optimized['totalKopecks'] - sequential['totalKopecks'])


def explain_plan(optimized, sequential, balances):
    changes = []
    for index, (chosen, baseline) in enumerate(zip(optimized['purchases'], sequential['purchases'], strict=True)):
        delta = chosen['cashbackKopecks'] - baseline['cashbackKopecks']
        if chosen['cardId'] != baseline['cardId'] or delta:
            changes.append(dict(purchaseIndex=index, optimized=chosen, sequential=baseline, deltaKopecks=delta))
    if optimized['totalKopecks'] == sequential['totalKopecks']:
        return dict(code='same_total', changes=changes)

    # Attribute a later increase to saved balance only when the card would
    # actually have less remaining at that point in the sequential allocation.
    for index, chosen in enumerate(optimized['purchases']):
        card = chosen['cardId']
        if card not in balances or chosen['cashbackKopecks'] <= sequential['purchases'][index]['cashbackKopecks']:
            continue
        optimized_prior = optimized['purchases'][:index]
        sequential_prior = sequential['purchases'][:index]
        def spent(rows):
            return sum(row['cashbackKopecks'] for row in rows if row['cardId'] == card)
        if chosen['cashbackKopecks'] <= balances[card] - spent(sequential_prior):
            continue
        saved_at = next((i for i, (before, after) in enumerate(zip(sequential_prior, optimized_prior, strict=True))
                         if before['cardId'] == card and after['cardId'] != card), None)
        if saved_at is not None:
            return dict(code='shared_limit', changes=changes, cardId=card, cardName=chosen['cardName'],
                        reserveFromPurchaseIndex=saved_at, useAtPurchaseIndex=index,
                        savedBalanceKopecks=spent(sequential_prior) - spent(optimized_prior))
    return dict(code='better_allocation', changes=changes)
