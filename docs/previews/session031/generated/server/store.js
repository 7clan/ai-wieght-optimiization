const fs = require('node:fs');
function createStore(filePath) {
  let list = [];
  let id = 0;
  return {
    list,
    create(body) {
      if (body.name === undefined || body.units === undefined) {
        throw new Error('Invalid body');
      }
      if (body.name.length === 0 || body.units <= 0) {
        throw new Error('Invalid body');
      }
      list.push({ id, name: body.name, units: body.units });
      id++;
      fs.writeFileSync(filePath, JSON.stringify(list));
      return { id, name: body.name, units: body.units };
    },
    delete(id) {
      if (id < 0 || id > list.length) {
        throw new Error('Invalid id');
      }
      list.splice(id, 1);
      fs.writeFileSync(filePath, JSON.stringify(list));
      return true;
    },
  };
}
module.exports = createStore;