def transform(payload):
    tasks = payload.get('tasks', [])
    total = len(tasks)
    # Count tasks where done is true.
    completed = sum(1 for task in tasks if task.get('done', False))
    return {'total': total, 'completed': completed, 'remaining': total - completed}
