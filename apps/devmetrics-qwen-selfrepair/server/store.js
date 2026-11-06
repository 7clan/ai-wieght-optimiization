const fs = require('node:fs');
function createStore(filePath) {
    const fileExists = fs.existsSync(filePath);
    if (!fileExists) {
        const data = [];
        fs.writeFileSync(filePath, JSON.stringify(data));
    }
    const data = fs.readFileSync(filePath, 'utf8');
    const dataObj = JSON.parse(data);
    return {
        list: () => dataObj,
        create: (entry) => {
            if (entry.project.length === 0 || entry.minutes === 0 || entry.date.length === 0 || entry.note.length === 0) {
                throw new Error('Invalid entry');
            }
            const id = `${Date.now()}`;
            const entryObj = {
                id,
                project: entry.project,
                minutes: entry.minutes,
                date: entry.date,
                note: entry.note,
            };
            dataObj.push(entryObj);
            fs.writeFileSync(filePath, JSON.stringify(dataObj));
            return entryObj;
        },
        delete: (id) => {
            const newData = dataObj.filter((entry) => entry.id !== id);
            fs.writeFileSync(filePath, JSON.stringify(newData));
            return true;
        },
    };
}

module.exports = createStore;