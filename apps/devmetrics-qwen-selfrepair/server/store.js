const fs = require('node:fs');
function createStore(filePath) {
    const entry = {};
    if (fs.existsSync(filePath)) {
        const json = fs.readFileSync(filePath).toString();
        entry = JSON.parse(json);
    }
    else {
        entry = [];
    }
    return {
        list: () => entry,
        create(body) {
            const newEntry = {
                id: '',
                project: body.project,
                minutes: body.minutes,
                date: body.date,
                note: body.note,
            };
            if (newEntry.project === '' || newEntry.minutes === 0) {
                throw new Error('Invalid entry');
            }
            newEntry.id = `${newEntry.project}-${newEntry.minutes}-${newEntry.date}`;
            entry.push(newEntry);
            fs.writeFileSync(filePath, JSON.stringify(entry));
            return true;
        },
        delete(id) {
            const index = entry.findIndex((entry) => entry.id === id);
            if (index !== -1) {
                entry.splice(index, 1);
                fs.writeFileSync(filePath, JSON.stringify(entry));
                return true;
            }
            return false;
        },
    };
}
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes: 10, date: '2020-01-01' }));
// console.log(store.create({ project: 'foo', minutes