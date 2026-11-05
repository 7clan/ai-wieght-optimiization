def transform(payload):
    items = payload.get('items', [])
    by_section = {}
    for item in items:
        section = item['section']
        by_section[section] = by_section.get(section, 0) + item['amount_cents']
    return {'count': len(items), 'total_cents': sum(item['amount_cents'] for item in items),
            'by_section': by_section}