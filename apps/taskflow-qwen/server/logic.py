def summarize_project(payload):
    total = 0
    done = 0
    remaining = 0
    percent = 0
    for task in payload["tasks"]:
        if task["status"] == "done":
            done += 1
        else:
            remaining += 1
        total += 1
        percent = 100 * done / total
    return {"total": total, "done": done, "remaining": remaining, "percent": percent}
