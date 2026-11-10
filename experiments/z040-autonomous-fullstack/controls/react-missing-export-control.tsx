// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: no default export.
// Proves invalid export fails closed.
export function NotDefault({ data }) {
  return <ul>{(data || []).map((row) => <li key={row.id}>{row.title}</li>)}</ul>;
}
