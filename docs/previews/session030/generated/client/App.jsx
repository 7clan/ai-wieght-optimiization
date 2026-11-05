const React = require('react');
function App() {
  const [expenses, setExpenses] = React.useState([]);
  const [summary, setSummary] = React.useState({count: 0, total_cents: 0, by_category: {}});
  const [description, setDescription] = React.useState('');
  const [amount, setAmount] = React.useState('');
  const [category, setCategory] = React.useState('other');
  const [notice, setNotice] = React.useState('');

  async function refresh() {
    const [expensesResponse, summaryResponse] = await Promise.all([
      fetch('/api/expenses'), fetch('/api/summary')
    ]);
    if (!expensesResponse.ok || !summaryResponse.ok) throw new Error('Loading expenses failed');
    const expensesData = await expensesResponse.json();
    const summaryData = await summaryResponse.json();
    setExpenses(expensesData.expenses);
    setSummary(summaryData);
  }

  React.useEffect(() => {
    refresh().catch(error => setNotice(error.message));
  }, []);

  async function addExpense(event) {
    event.preventDefault();
    const cents = Number(amount);
    if (!description.trim() || !Number.isInteger(cents) || cents <= 0) {
      setNotice('Enter a description and positive amount in cents.');
      return;
    }
    try {
      const response = await fetch('/api/expenses', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({description: description.trim(), amount_cents: cents, category})
      });
      if (!response.ok) throw new Error('Could not add expense');
      setDescription('');
      setAmount('');
      setNotice('Expense added.');
      await refresh();
    } catch (error) {
      setNotice(error.message);
    }
  }

  async function deleteExpense(id) {
    try {
      const response = await fetch('/api/expenses/' + encodeURIComponent(id), {method: 'DELETE'});
      if (!response.ok) throw new Error('Could not delete expense');
      setNotice('Expense deleted.');
      await refresh();
    } catch (error) {
      setNotice(error.message);
    }
  }

  return <div className="ledger">
    <header><p className="eyebrow">Your personal budget</p><h1>PocketLedger</h1>
      <p>Track small expenses and understand where your money goes.</p></header>
    <section className="summary">
      <h2>Overview</h2>
      <p className="total">{(summary.total_cents / 100).toFixed(2)}</p>
      <p>{summary.count} expenses recorded</p>
      <ul>{Object.entries(summary.by_category).map(([name, cents]) =>
        <li key={name}>{name}: {(cents / 100).toFixed(2)}</li>)}</ul>
    </section>
    <section><h2>Add an expense</h2>
      <form onSubmit={addExpense}>
        <label>Description<input aria-label="Description" value={description}
          onChange={event => setDescription(event.target.value)} /></label>
        <label>Amount in cents<input aria-label="Amount in cents" type="number" min="1"
          value={amount} onChange={event => setAmount(event.target.value)} /></label>
        <label>Category<select value={category} onChange={event => setCategory(event.target.value)}>
          <option value="other">Other</option><option value="food">Food</option>
          <option value="travel">Travel</option></select></label>
        <button type="submit">Add Expense</button>
      </form>
      <p aria-live="polite">{notice}</p>
    </section>
    <section><h2>Recent expenses</h2>
      {expenses.length === 0 ? <p>No expenses yet.</p> : <ul>{expenses.map(expense =>
        <li key={expense.id}><span>{expense.description} · {expense.category}
          · {(expense.amount_cents / 100).toFixed(2)}</span>
          <button type="button" onClick={() => deleteExpense(expense.id)}>Delete</button>
        </li>)}</ul>}
    </section>
  </div>;
}
module.exports = {App};