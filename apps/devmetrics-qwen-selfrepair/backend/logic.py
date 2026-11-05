def summarize(payload):
    entries = payload.get('entries')
    if entries is None:
        return 0, {}, {}, 0, None
    # YOUR CODE HERE
    entries = sorted(entries, key=lambda entry: entry['minutes'], reverse=True)
    by_project = {}
    by_day = {}
    for entry in entries:
        project = entry['project']
        if project not in by_project:
            by_project[project] = entry['minutes']
        else:
            by_project[project] += entry['minutes']
        date = entry['date']
        if date not in by_day:
            by_day[date] = entry['minutes']
        else:
            by_day[date] += entry['minutes']
    active_projects = len(by_project)
    busiest_day = None
    if active_projects > 0:
        busiest_day = max(by_day, key=lambda date: by_day[date])
    return {
        'total_minutes': sum(by_project.values()),
        'by_project': by_project,
        'by_day': by_day,
        'active_projects': active_projects,
        'busiest_day': busiest_day
    }

# NEW DEVMETRICS TASK. Return the project with the highest minutes, or
# None if no project has any minutes.
# PUBLIC EXAMPLE:
# highest_project({"entries":[{"project":"api-server","minutes":95,"date":"2026-11-03"},
# {"project":"docs","minutes":60,"date":"2026-11-03"}]})
