const fs = require('node:fs');
function createStore(filePath) {
  let data = fs.readFileSync(filePath).toString();
  let entries = JSON.parse(data);
  return {
    list: function () {
      return entries;
    },
    create: function (body) {
      if (body.project.length === 0 || body.minutes === 0 || body.date.length === 0) {
        throw new Error('Invalid entry');
      }
      if (body.project.length < 1 || body.minutes < 1 || body.date.length < 1) {
        throw new Error('Invalid entry');
      }
      if (body.project === '' && body.minutes === 0 && body.date === '') {
        throw new Error('Invalid entry');
      }
      let id = entries.length.toString();
      if (entries[id] !== undefined) {
        throw new Error('Duplicate entry');
      }
      body.id = id;
      entries.push(body);
      data = JSON.stringify(entries);
      fs.writeFileSync(filePath, data);
      return body;
    },
    delete: function (id) {
      if (id.length < 1) {
        throw new Error('Invalid entry');
      }
      if (id.length > 1) {
        throw new Error('Invalid entry');
      }
      if (id === '') {
        throw new Error('Invalid entry');
      }
      if (entries[id] === undefined) {
        throw new Error('Invalid entry');
      }
      entries.splice(id, 1);
      data = JSON.stringify(entries);
      fs.writeFileSync(filePath, data);
      return true;
    },
  };
}