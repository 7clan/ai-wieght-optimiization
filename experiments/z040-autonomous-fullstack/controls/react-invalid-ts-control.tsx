// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: TypeScript syntax
// error. Proves transpile failure fails closed.
export default function ListView({ data ) {
  return <ul>{(data || []).map((row) => <li>{row.title}</li>)}</ul>;
}
