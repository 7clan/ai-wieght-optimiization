const fs = require('node:fs');
function createStore(filePath) {
  function read() {
    if (!fs.existsSync(filePath)) return [];
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  }
  function write(items) {
    fs.writeFileSync(filePath, JSON.stringify(items, null, 2));
  }
  return {
    list() {
      return read();
    },
    create(body) {
      if (!body || typeof body.description !== 'string' ||
          !body.description.trim() || !Number.isInteger(body.amount_cents) ||
          body.amount_cents <= 0) {
        throw new Error('Description and positive integer amount required');
      }
      const items = read();
      const id = String(items.reduce((max, row) => Math.max(max, Number(row.id) || 0), 0) + 1);
      const expense = {
        id,
        description: body.description.trim(),
        amount_cents: body.amount_cents,
        category: ['food', 'travel', 'other'].includes(body.category) ? body.category : 'other'
      };
      items.push(expense);
      write(items);
      return expense;
    },
    delete(id) {
      const items = read();
      const filtered = items.filter(row => row.id !== String(id));
      if (filtered.length === items.length) return false;
      write(filtered);
      return true;
    }
  };
}
