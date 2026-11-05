def transform(payload):
    expenses = payload.get('expenses', [])
    by_category = {}
    for expense in expenses:
        category = expense['category']
        by_category[category] = by_category.get(category, 0) + expense['amount_cents']
    return {'count': len(expenses), 'total_cents': sum(expense['amount_cents'] for expense in expenses),
            'by_category': by_category}