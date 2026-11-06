const React = require('react');
function App() {
    const [entries, setEntries] = React.useState([]);
    const [form, setForm] = React.useState({ project: '', minutes: '', date: '', note: '' });
    const [filter, setFilter] = React.useState([]);
    const [summary, setSummary] = React.useState({});
    const [offline, setOffline] = React.useState(false);
function load() {
    fetch('/api/entries')
        .then((response) => response.json())
        .then((entries) => {
            setEntries(entries);
        });
    fetch('/api/summary')
        .then((response) => response.json())
        .then((summary) => {
            setSummary(summary);
        });
}
    React.useEffect(() => {
        load();
    }, []);
    const handleInputChange = ({ target }) => {
        const { name, value } = target;
        setForm((f) => ({
            ...f,
            [name]: value,
        }));
    };
    const handleFormSubmit = ({ target }) => {
        const { name, value } = target;
        setForm((f) => ({
            ...f,
            [name]: value,
        }));
    };
    const handleProjectChange = (project) => {
        setFilter((f) => ({
            ...f,
            project: project,
        }));
    };
    const handleSummaryChange = (value) => {
        setSummary((s) => ({
            ...s,
            [value]: value,
        }));
    };
    const handleOfflineChange = (offline) => {
        setOffline(offline);
    };
    const handleFilterChange = (filter) => {
        setFilter((f) => ({
            ...f,
            filter: filter,
        }));
    };
const handleSubmit = async (e) => {
    e.preventDefault();
    try {
        const response = await fetch('/api/entries', { method: 'POST', headers: {
            'Content-Type': 'application/json' }, body: JSON.stringify(form) });
        if (!response.ok) throw new Error('offline');
        load();
    } catch (error) {
        console.error('Error submitting form:', error);
    }
};
    const handleAdd = (e) => {
        e.preventDefault();
        const { id } = form;
        const newEntry = {
            id,
            project: form.project,
            minutes: form.minutes,
            date: form.date,
            note: form.note,
        };
        setEntries([...entries, newEntry]);
        setForm({ project: '', minutes: '', date: '', note: '' });
        load();
    };
    const handleDelete = (id) => {
        const newEntries = entries.filter((entry) => entry.id !== id);
        setEntries(newEntries);
    };
    return (
        <div>
            {offline ?
                <h1>Offline Demo Mode</h1> :
                <div>
                    <h1>React Demo</h1>
                    <div>
                        <h2>Entries</h2>
                        <div>
                            <ul>
                                {entries.map((entry) => (
                                    <li key={entry.id}>
                                        <span>
                                            <span>{entry.project}</span>
                                            <span>{entry.minutes}</span>
                                            <span>{entry.date}</span>
                                            <span>{entry.note}</span>
                                        </span>
                                        <span>
                                            <button onClick={() => handleDelete(entry.id)}>Delete</button>
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <div>
                            <form onSubmit={handleSubmit}>
                                <label>
                                    Project:
                                    <input type="text" name="project" value={form.project} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Minutes:
                                    <input type="number" name="minutes" value={form.minutes} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Date:
                                    <input type="date" name="date" value={form.date} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Note:
                                    <input type="text" name="note" value={form.note} onChange={handleInputChange} />
                                </label>
                                <input type="submit" value="Submit" />
                            </form>
                        </div>
                        <div>
                            <form onSubmit={handleAdd}>
                                <label>
                                    Project:
                                    <input type="text" name="project" value={form.project} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Minutes:
                                    <input type="number" name="minutes" value={form.minutes} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Date:
                                    <input type="date" name="date" value={form.date} onChange={handleInputChange} />
                                </label>
                                <label>
                                    Note:
                                    <input type="text" name="note" value={form.note} onChange={handleInputChange} />
                                </label>
                                <input type="submit" value="Add" />
                            </form>
                        </div>
                        <div>
                            <h2>Summary</h2>
                            <div>
                                {summary.map((value, index) => (
                                    <div key={index}>
                                        <span>{index}</span>
                                        <span>{value}</span>
                                    </div>
                                ))}
                            </div>
                            <div>
                                <button onClick={handleOfflineChange.bind(this, !offline)}>Toggle Offline Mode</button>
                            </div>
                        </div>
                    </div>
                    <div>
                        <h2>Filter</h2>
                        <div>
                            <select value={filter.filter} onChange={handleFilterChange}>
                                <option value="all">All</option>
                                <option value="api-server">API Server</option>
                                <option value="mobile-ui">Mobile UI</option>
                                <option value="docs">Docs</option>
                            </select>
                        </div>
                        <div>
                            <input value={form.project} onChange={handleProjectChange} placeholder="Project" />
                        </div>
                        <div>
                            <input value={form.minutes} onChange={handleInputChange} placeholder="Minutes" />
                        </div>
                        <div>
                            <input value={form.date} onChange={handleInputChange} placeholder="Date" />
                        </div>
                        <div>
                            <input value={form.note} onChange={handleInputChange} placeholder="Note" />
                        </div>
                    </div>
                </div>
            }
        </div>
    );
}
module.exports = App;